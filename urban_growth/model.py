import numpy as np
from skimage import morphology
from scipy.spatial import distance
from scipy.special import expit
from scipy.ndimage.filters import gaussian_filter

class settlement_model:

	def __init__(self, M0 = None, geo = None, D = None):

		if geo is not None:
			self.geo = geo
		elif M0 is not None:
			self.geo = np.ones(self.M0.shape)

		if D is not None: 
			self.D = D

		self.dists     = None
		self.dist_type = None
		self.dist_mode = None
		self.dist_truncation = None

	def set_M0(self, M0 = None, **kwargs):
		if M0 is not None:
			self.M0 = M0
		else:
			self.M0 = random_mat(**kwargs)

		self.M = self.M0.copy()

	def get_M0(self):
		return self.M0

	def get_M(self):
		return self.M

	def settlement_type_matrix(self, thresh, stage = 'current'):
		if stage == 'current': 
			M_d = self.M

		elif stage == 'initial':
			M_d = self.M0

		rural, urban, unsettled = settlement_types(M_d, thresh = thresh)
		types = np.zeros(M_d.shape)

		for i in range(urban.shape[0]):
			types[tuple(urban[i,])] =  1
		for i in range(rural.shape[0]):
			types[tuple(rural[i,])] = -1		

		return types

	def set_dists(self, thresh, stage = 'current', mode = 'full', truncation = None):
		
		print 'recalculating distances'
		if stage == 'initial': 
			self.dists = get_dists(self.M0, thresh, mode, truncation)	
			
		elif stage == 'current':
			self.dists = get_dists(self.M, thresh, mode, truncation)
		
		self.dist_type = stage
		self.dist_mode = mode
		self.dist_truncation = truncation

	def density(self, thresh, pars, use_geo = False, stage = 'current', mode = 'full', truncation = None):
		
		pars = {k : float(pars[k]) for k in pars}  # had a float bug in here somewhere

		redo_dists = (self.dist_mode != mode) |  (stage == 'current') | (stage == 'initial') & (self.dist_type != 'initial') | (truncation != self.dist_truncation)
		
		if redo_dists:
			self.set_dists(thresh, stage, mode, truncation)
		
		gammas = ('gamma_r', 'gamma_u')
		g_pars = {k: pars[k] for k in gammas}
		p_pars = {k: pars[k] for k in pars if k not in gammas}
		
		if stage == 'initial': 
			M_d = self.M0
		elif stage == 'current':
			M_d = self.M

		w_rural, w_urban = distance_weights(M_d, self.dists, thresh, **g_pars) 
		
		probs = model_1_probs(w_rural, w_urban, **p_pars) 
		if use_geo:
			probs = probs * self.geo

		return probs

	

def model_1_probs(w_rural, w_urban, alpha_r, beta_r, alpha_u, beta_u):
	p_r = expit(alpha_r * w_rural + beta_r)
	p_u = expit(alpha_u * w_urban + beta_u)

	denom = p_r + p_u

	return p_r ** 2 / denom, p_u ** 2 / denom

def id_clusters(M):

	mask = morphology.label(M, connectivity = 1)
	return mask

def cluster_areas(mask, centroids = False):
	
	u = np.unique(mask, return_counts = True)

	def centroid(i):
		ix = np.where(mask == i)
		return np.array(ix).mean(axis = 1)

	def f(i):
		if centroids:
			return np.concatenate((np.array([u[1][i]]), centroid(i)))
		else:
			return u[1][i]

	area_dict = {u[0][i] : f(i) for i in range(len(u[0]))} # needs to be sorted?
	area_dict.pop(0) # ignore background
	return area_dict

def settlement_types(M,  return_type = 'cell', thresh = 0, centroids = False):
	'''
		Compute the types of cells and return the results at either the cluster or cell level. 
	'''

	mask      = id_clusters(M)
	area_dict = cluster_areas(mask, centroids)
	
	if centroids & (return_type == 'cluster'):
		urban_clusters = {key : area_dict[key] for key in area_dict if area_dict[key][0] >= thresh}
	else:
		urban_clusters = {key : area_dict[key] for key in area_dict if area_dict[key] >= thresh}
	
	rural_clusters = area_dict

	for key in urban_clusters:
		rural_clusters.pop(key, None) 

	if return_type == 'cluster':
		return np.array(rural_clusters.values()), np.array(urban_clusters.values())

	else:
		ix = np.in1d(mask.ravel(), urban_clusters.keys()).reshape(mask.shape)
		a = np.where(ix)

		urban_cells = np.array([[a[0][i], a[1][i]] for i in range(len(a[0]))])

		ix = np.in1d(mask.ravel(), rural_clusters.keys()).reshape(mask.shape)
		a = np.where(ix)

		rural_cells = np.array([[a[0][i], a[1][i]] for i in range(len(a[0]))])

		a = np.where(mask == 0)
		unsettled_cells = np.array([[a[0][i], a[1][i]] for i in range(len(a[0]))])

		return rural_cells, urban_cells, unsettled_cells

def get_dists(M, thresh = 0, mode = 'full', truncation = None):
	
	def f(j, arr):
			a = np.unique(arr[j,], return_counts=True)
			if truncation is not None:
				out = np.array([[a[0][i], a[1][i]] for i in range(a[0].shape[0]) if a[0][i] <= truncation])
				if len(out) == 0:
					out = np.array([[1,0]])
				return out
			else:
				return np.array([[a[0][i], a[1][i]] for i in range(a[0].shape[0])])

	if mode == 'full':
		
		rural, urban, unsettled = settlement_types(M, 'cell', thresh)
		
		rural_dist_mat = distance.cdist(unsettled, rural, 'euclidean').astype(int)
		rural_dists    = {i : f(i, rural_dist_mat) for i in range(rural_dist_mat.shape[0])}

		urban_dist_mat = distance.cdist(unsettled, urban, 'euclidean').astype(int)
		urban_dists    = {i : f(i, urban_dist_mat) for i in range(urban_dist_mat.shape[0])}

		return rural_dists, urban_dists

	if mode == 'centroid':
		rural_clusters, urban_clusters = settlement_types(M, 'cluster', thresh, True)
		rural_cells, urban_cells, unsettled_cells = settlement_types(M, 'cell', thresh)

		rural_dist_mat = distance.cdist(unsettled_cells, rural_clusters[:,1:], 'euclidean').astype(int)
		urban_dist_mat = distance.cdist(unsettled_cells, urban_clusters[:,1:], 'euclidean').astype(int)

		rural_dists    = {i : f(i, rural_dist_mat) for i in range(rural_dist_mat.shape[0])}
		urban_dists    = {i : f(i, urban_dist_mat) for i in range(urban_dist_mat.shape[0])}

		return rural_dists, urban_dists

def distance_weights(M, dists, thresh, gamma_r, gamma_u):
	def f(i, gamma_r, gamma_u):
		
		a = np.array(dists[0][i])
		r = np.dot(a[:,0] ** (-gamma_r), a[:,1])

		b = np.array(dists[1][i])
		u = np.dot(b[:,0] ** (-gamma_u), b[:,1])
		
		return r, u
	
	rural, urban, unsettled = settlement_types(M, 'cell', thresh)
	
	weights_rural = np.empty(M.shape)
	weights_urban = np.empty(M.shape)
	weights_rural.fill(np.nan)
	weights_urban.fill(np.nan)

	weight_tuples = [f(i, gamma_r, gamma_u) for i in range(len(dists[0]))]

	for i in range(unsettled.shape[0]):
		weights_urban[unsettled[i][0], unsettled[i][1]] = weight_tuples[i][1]
		weights_rural[unsettled[i][0], unsettled[i][1]] = weight_tuples[i][0]

	return weights_rural, weights_urban

def random_mat(L, density = .5, blurred = True, blur = 3, central_city = True):
	
	M = np.random.rand(L, L)

	if central_city:

		M[(1 * L/2 - L / 10):(1 * L/2 + L/10),(1 * L/2 - L / 10):(1 * L/2 + L/10)] = 0

	if blurred: 
		M = gaussian_filter(M, blur)
		
	ix_low = M < density  # Where values are low
	M[ix_low]  = 1

	M[M < 1] = 0
		
	return M
