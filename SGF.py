from __future__ import print_function
import re
import os
import string

class SGFParseError(Exception):
	def __init__(self, pos, expected, found, context):
		self.values = pos, expected, found, context
	def __str__(self):
		return "Error parsing SGF at position {}. Expected '{}', found '{}'\nContext: {}\n".format(self.values)

class SGFValidationError(Exception):
	def __init__(self, pos, reason):
		self.values = pos, reason
	def __str__(self):
		return "Error validating SGF at position {}.\nReason: {}\n".format(self.values)


class SGFParser:
	"""
	The parser returns a list (collection, potentially empty) of
	tuples (gametrees), where each such tuple consists of
	 1. A non-empty list (sequence) of dictionaries (nodes), with zero or more
		keys (properties) pointing to a list (values, zero or more)
	 2. Optionally another list (gametrees for variations)
	"""

	value_re  = re.compile(r'\[(?:\\.|[^\\\]])*\]', re.DOTALL) # everything from a starting '[' up to next unescaped ']'
	ff4_propid_re = re.compile(r'[A-Z]+')
	old_propid_re = re.compile(r'[A-Za-z]+') # propidents used in FF 1-3
	space_re  = re.compile(r'\s+')
	verbosity = 1

	root_properties = {
		'AP':('Application',     'compose(simpletext:simpletext)' ),
		'CA':('Charset',         'simpletext'                     ),
		'FF':('Fileformat',      'number'                         ),
		'GM':('Gametype',        'number'                         ),
		'ST':('Variation Style', 'number'                         ),
		'SZ':('Board Size',      'number|compose(number:number)')
	}

	def __init__(self):
		self.data = ''
		self.pos = 0

	def parseDir(self, path, recurse=False):
		"""Add SGF Data from all sgf files in a directory"""
		games = []
		for root, dirs, files in os.walk(path):
			if not recurse:
				dirs[:] = []
			sgfpaths = [os.path.join(root, f) for f in files if f.endswith('.sgf')]
			games.extend(self.parseFiles(sgfpaths))
		return games

	def parseFiles(self, pathlist):
		"""Add SGF data from a list of files, one by one"""
		games = []
		for path in pathlist:
			games.extend(self.parseFile(path))
		return games

	def parseFile(self, path):
		"""Add SGF data from a file"""
		try:
			with open(path, 'r') as f:
				sgf = f.read()
			collection = self.parse(sgf)
			if self.verbosity > 1:
				print("Parsed file {} successfully".format(path))
			return collection
		except IOError:
			if self.verbosity > 0:
				print("Failed to open file {}".format(path))
		except SGFParseError:
			if self.verbosity > 0:
				print("SGF parsing error in file {}".format(path))
			raise
			
	def parse(self, sgf):
		"""Parse games from SGF data in a string."""

		self.data = sgf
		self.pos = 0

		try:
			collection = self.parseCollection()
		except SGFParseError:
			if self.verbosity > 2:
				print("Error parsing Collection")
			raise
		finally:
			self.data = ''
			self.pos = 0

		if self.verbosity > 2:
			print("Reached end of data with no errors. SGF succesfully parsed")

		return collection
	
	@property
	def nextToken(self):
		"""Return next non-whitespace character from current position, or None at end"""
		space = self.space_re.match(self.data, self.pos)
		if space:
			self.pos += len(space.group(0))
		return self.data[self.pos] if self.pos < len(self.data) else None
	
	@property
	def context(self):
		return self.data[max(0,self.pos-10):min(self.pos+10, len(self.data))]

	def parseCollection(self):
		"""Return a list of game trees (SGF Spec: Collection)"""
		collection = []
		while self.nextToken != None or not collection:
			self.gm = 1 # default game type
			self.ff = 1 # default file format
			self.propid_re = self.old_propid_re # only if we find and FF[4] tage do we switch to ff4
			try:
				collection.append(self.parseGameTree(root=True))
				if self.verbosity > 4:
					print("Parsed game tree succesfully")
			except SGFParseError:
				if self.verbosity > 3:
					print("Error parsing game tree {}".format(len(collection)+1))
				raise
		if self.verbosity > 3:
			print("Parsed {} game trees succesfully".format(len(collection)))
		return collection
	
	def parseGameTree(self, root=False):
		"""Return a tuple of a sequence and (optionally) a list of subtrees"""
		if self.nextToken != '(':
			raise SGFParseError(self.pos, '(', self.nextToken, self.context)
		self.pos += 1;
		subtrees = []
		try:
			seq = self.parseSequence(root)
		except SGFParseError:
			if self.verbosity > 5:
				print("Error parsing sequence")
			raise
	
		while self.nextToken != ')':
			try:
				subtrees.append(self.parseGameTree())
			except SGFParseError:
				if self.verbosity > 5:
					print("Error parsing variation")
				raise
		self.pos += 1 # the loop correctly ended on a closing parenthesis, skip that
		if subtrees:
			return seq, subtrees
		else:
			return seq,
	
	def parseSequence(self, root=False):
		"""Return a list of nodes."""
		nodes=[]
		while self.nextToken == ';' or not nodes:
			try:
				nodes.append(self.parseNode(root and not nodes))
			except SGFParseError:
				if self.verbosity > 6:
					print("Error parsing node")
				raise
		return nodes
	
	def parseNode(self, root=False):
		"""Return a dictionary of properties."""
		if self.nextToken != ';':
			raise SGFParseError(self.pos, ';', self.nextToken, self.context)
		self.pos += 1
		properties = {}
		while self.propid_re.match(self.nextToken):
			try:
				propident, propvalues = self.parseProperty(root)
			except SGFParseError:
				if self.verbosity > 7:
					print("Error parsing property")
				raise
			if propident in properties:
				print("{} duplicated at {}. {}".format(propident, self.pos, self.context))
				raise SGFValidationError(self.pos, "Duplicate property in the same node")
			else:
				properties[propident] = propvalues
			# FF and GM affect how the game is parsed
			if propident == 'FF':
				if len(propvalues) == 1 and 1 <= int(propvalues[0]) <= 4:
					self.ff = int(propvalues[0])
					if self.ff == 4:
						self.propid_re = self.ff4_propid_re
				else:
					raise SGFValidationError(self.pos, "Illegal value for FF property. Should be number in range 1-4")
			if propident == 'GM':
				if len(propvalues) == 1 and 1 <= int(propvalues[0]):
					self.gm = int(propvalues[0])
				else:
					raise SGFValidationError(self.pos, "Illegal value for GM property. Should be a number")
		if root and not self.ff:
			self.ff = 1
		return properties

	def parseProperty(self, root=False):
		try:
			propident = self.parsePropIdent()
		except SGFParseError:
			if self.verbosity > 8:
				print("Error parsing property ident")
			raise
		if propident in self.root_properties and not root:
			raise SGFValidationError(self.pos, "Illegal root-property {} in non-root node".format(propident))

		propvalues = []
		while self.nextToken == '[' or not propvalues:
			try:
				propvalues.append(self.parsePropValue())
			except SGFParseError:
				if self.verbosity > 8:
					print("Error parsing property value")
				raise
		return propident, propvalues

	def parsePropIdent(self):
		propmatch = self.propid_re.match(self.data, self.pos)
		if not propmatch:
			raise SGFParseError(self.pos, '[A-Z]', self.nextToken, self.context)
		self.pos += len(propmatch.group(0))
		propident = "".join(ch for ch in propmatch.group(0) if ch.isupper()) # filter out lowercase chars allowed in FF 1-3
		return propident

	def parsePropValue(self):
		"""Return a list of property value strings."""
		if self.nextToken != '[':
			raise SGFParseError(self.pos, '[', self.nextToken, self.context)
		valuematch = self.value_re.match(self.data, self.pos)
		if valuematch:
			self.pos += len(valuematch.group(0))
			return valuematch.group(0)[1:-1]
		else:
			# value_re failed, therefore no closing bracket was found before EOF. Skip to end and raise error.
			self.pos = len(self.data) - 1
			raise SGFParseError(self.pos, ']', self.nextToken, self.context)

