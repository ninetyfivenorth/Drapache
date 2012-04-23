"""
Implements the interaction with the dropbox api
"""
import dropbox

import dbpyexecute
import index_generator
import util
from util import ResponseObject,DropacheException

import os.path
import re




#for dev
import pprint
#



class FileServer:
	"""
	The class responsable for hitting the dropbox and processing the results
	
	most of the power of the service will come from here
	"""
	
	
	def __init__(self,client,request):
		self.client = client
		self.request = request
		
	def serve(self,path):
		"""
		serves the given path, returning a Response Object
		
		some special rules
		- if it is a directory,
			returns an indexed list of the files
		- if it is a directory without a trailing slash,
			returns a redirect request (these will also be able to come fro)
		"""
		
		#anything prefixed with '_' is not accessable
		path_components = path.split('/')
		for component in path_components:
			if component.startswith('_'):
				return ResponseObject(403,'Forbidden',error=True)
		
		
		try:
			meta_info = self.client.metadata(path)
			
			#### checking for the is_Deleted flag
			try:
				if meta_info['is_deleted']:
					raise DropacheException(410,"File is deleted")
			except KeyError:
				pass #its not deleted
			
			if meta_info['is_dir']:
				#that means we are dealing with a directory
				#first check if it doesn't end with a slash
				if not path.endswith('/'):
					redirect_location = path+'/'
					if self.request.query_string:
						redirect_location += '?'+self.request.query_string
						
					return ResponseObject(301,'redirect',headers={'Location':redirect_location})
				else:
					return self._find_and_serve_index(meta_info,path)
			
			else:
				#serve file handles the routing of pyhton vs file
				return self._serve_file(meta_info)

				
		except dropbox.rest.ErrorResponse as e:
			return ResponseObject(e.status,e.reason,headers=e.headers,error=True)
			
		except DropacheException as e:
			return ResponseObject(e.status,e.message,error=True)
			
	def _serve_file(self,file_meta):
		#here is where special handling must be invoked
		if file_meta['path'].endswith('.dbpy'):
			return self._serve_python(file_meta)
		else:			
			return self._serve_static(file_meta)
		
	
	def _serve_static(self,file_meta):
		"""
		downloads and serves the file in path
		"""
		path = file_meta['path']
		f = self.client.get_file(path).read()
		if f.startswith('#DBPYEXECUTE'):
			param_dict = dict(client=self.client,request=self.request)
			return dbpyexecute.execute(f,**param_dict)
		headers = {'Content-type':self._get_content_type(file_meta)}
		return ResponseObject(200,f,headers)
		
		
	def _serve_python(self,file_meta):
		path = file_meta['path']
		f = self.client.get_file(path).read()
		if f.startswith("#NOEXECUTE"):
			#allows these files to be shared without getting executed
			headers = {'Content-type':'text/plain'}
			return ResponseObject(200,f,headers)
		
		param_dict = dict(client=self.client,request=self.request)
		return dbpyexecute.execute(f,**param_dict)

	
	def _find_and_serve_index(self,directory_meta,path):
		"""
		called when asked to serce a directory
		check for the presence of an index file and serve it (without redirect of course)
		or present an index if there isn't one
		lets lok through meta_info[contents], anything with index is of interest
		precedence is .dbpy, .html, .txt, and thats it
		
		for now, just auto generate an index, fun!
		"""
		extensions_precedence = ('dbpy','html','txt')
		
		#build the re
		re_string = "^index\.(%s)$"%( '|'.join(extensions_precedence) )
		index_re = re.compile(re_string)
		
		index_paths = {}
		
		for file_meta in directory_meta['contents']:
			file_path = file_meta['path']
			base_name = os.path.basename(file_path)
			
			index_re_match = index_re.match(base_name)
			
			if index_re_match:
				match_type = index_re_match.group(1)
				index_paths[match_type] = file_meta
				
		
		for extension in extensions_precedence:
			if extension in index_paths:
				return self._serve_file(index_paths[extension])
			
		
		return ResponseObject(200,index_generator.get_index_file(directory_meta['contents'],path,self.client))
		
		
	def _get_content_type(self,file_meta):
		given = file_meta['mime_type']
		if given.startswith('text/x-'):
			return 'text/plain'
		else:
			return given
		
		

