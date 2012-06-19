from __future__ import print_function
import re
import os
import string

class SGFParseError(Exception):
	def __init__(self, pos, expected, found, context):
		self.values = pos, expected, found, context
	def __str__(self):
		return "Error parsing SGF at position {}. Expected '{}', found '{}'\nContext: {}\n".format(self.values)

class SGFParser:
	"""
	The parser returns a list (collection, potentially empty) of
	tuples (gametrees), where each such tuple consists of
	 1. A non-empty list (sequence) of dictionaries (nodes), with zero or more
		keys (properties) pointing to a list (values, zero or more)
	 2. Optionally another list (gametrees for variations)
	Deviations from the standard:
	The parser is a little more lenient than the standard. Specifically, if
	the same property appears in the same node multiple times, the values are
	merged with the earlier value list. The standard considers this an error.
	Note that, due to the merging, each property will be unique after
	parsing, so if you write it out again, it will be legal.
	"""

	value_re  = re.compile(r'\[(?:\\.|[^\\\]])*\]', re.DOTALL) # everything from a starting '[' up to next unescaped ']'
	propid_re = re.compile(r'[A-Z]+')
	space_re  = re.compile(r'\s+')
	verbosity = 1

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
		# skip whitespace first
		space = self.space_re.match(self.data, self.pos)
		if space:
			self.pos += len(space.group(0))
		return self.data[self.pos] if self.pos < len(self.data) else None
	
	@property
	def context(self):
		return self.data[max(0,self.pos-10):min(self.pos+10, len(self.data))]

	def parseCollection(self):
		"""Keep trying to parse a game tree until EOF is reached.
		Return a list of game trees (SGF Spec: Collection)
		"""
		
		collection = []
		while self.nextToken != None or not collection:
			try:
				collection.append(self.parseGameTree())
				if self.verbosity > 4:
					print("Parsed game tree succesfully")
			except SGFParseError:
				if self.verbosity > 3:
					print("Error parsing game tree {}".format(len(collection)+1))
				raise
		if self.verbosity > 3:
			print("Parsed {} game trees succesfully".format(len(collection)))
		return collection
	
	def parseGameTree(self):
		"""Parse a Game Tree. 
		Returns a tuple of a sequence and (optionally) a list of subtrees
		
		"""
		
		if self.nextToken != '(':
			raise SGFParseError(self.pos, '(', self.nextToken, self.context)
		self.pos += 1;
		subtrees = []
		try:
			seq = self.parseSequence()
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
	
	def parseSequence(self):
		nodes=[]
		while self.nextToken == ';' or not nodes:
			try:
				nodes.append(self.parseNode())
			except SGFParseError:
				if self.verbosity > 6:
					print("Error parsing node")
				raise
		return nodes
	
	def parseNode(self):
		if self.nextToken != ';':
			raise SGFParseError(self.pos, ';', self.nextToken, self.context)
		self.pos += 1
		properties = {}
		while self.nextToken in string.ascii_uppercase:
			propident = self.propid_re.match(self.data, self.pos).group(0)
			self.pos += len(propident)
			valuelist = []
			while self.nextToken == '[' or not valuelist:
				try:
					valuelist.append(self.parsePropValue())
				except SGFParseError:
					if self.verbosity > 7:
						print("Error parsing first node value")
					raise
			if propident in properties:
				# the standard considers this an error
				properties[propident].extend(valuelist)
			else:
				properties[propident] = valuelist
		return properties

	def parsePropValue(self):
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

