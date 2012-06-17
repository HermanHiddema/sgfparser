from __future__ import print_function
import re

class SGFParseError(Exception):
	def __init__(self, pos, expected, found, context):
		self.values = pos, expected, found, context
	def __str__(self):
		return "Error parsing SGF at position {}. Expected '{}', found '{}'\nContext: {}\n".format(self.values)

class Parser:
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

	value_re  = re.compile(r'(?:\\.|[^\\\]])+\]', re.DOTALL) # everything up to next unescaped ']'
	propid_re = re.compile(r'[A-Z]+')
	space_re  = re.compile(r'\s+')
	verbosity = 1

	def __init__(self):
		self.games = []
		self.data = ''
		self.pos = 0

	def parseFromDir(self, dirname, recurse=False):
		"""Add SGF Data from all sgf files in a directory"""
		pass #TODO

	def parseFromFiles(self, files):
		"""Add SGF data from a list of files, one by one"""
		allgames = []
		for f in files:
			allgames.append(self.parseFromFile(f))

		return allgames

	def parseFromFile(self, filename):
		"""Add SGF data from a file"""
		try:
			with open(filename, 'r') as f:
				sgf = f.read()
			collection = self.parse(sgf)
			if self.verbosity > 1:
				print("Parsed file {} successfully".format(filename))
			return collection
		except IOError:
			if self.verbosity > 0:
				print("Failed to open file {}".format(filename))
		except SGFParseError:
			if self.verbosity > 0:
				print("SGF parsing error in file {}".format(filename))
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

		self.games.extend(collection)
		return collection
	
	@property
	def nextToken(self):
		return self.data[self.pos] if self.pos < len(self.data) else None
	
	@property
	def context(self):
		return self.data[max(0,self.pos-10):min(self.pos+10, len(self.data))]
	
	def skipWhiteSpace(self):
		"""Helper function to skip white-space"""

		space = self.space_re.match(self.data, self.pos)
		if space:
			self.pos += len(space.group(0))

	def parseCollection(self):
		"""Keeps trying to parse a game tree until EOF is reached.
		Returns a list of game trees (SGF Spec: Collection)
		"""
		
		collection = []
		self.skipWhiteSpace()
		while True:
			try:
				gt = self.parseGameTree()
				collection.append(gt)
				if self.verbosity > 4:
					print("Parsed game tree succesfully")
			except SGFParseError:
				if self.verbosity > 3:
					print("Error parsing game tree {}".format(len(collection)+1))
				raise
			self.skipWhiteSpace()
			if self.nextToken == None: 
				break # reached EOF after at least one game
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
	
		pos = self.skipWhiteSpace()
		while self.nextToken != ')':
			try:
				gt = self.parseGameTree()
			except SGFParseError:
				if self.verbosity > 5:
					print("Error parsing variation")
				raise
			subtrees.append(gt)
			self.skipWhiteSpace()
		# the loop correctly ended on a closing parenthesis, skip that
		self.pos += 1
		if subtrees:
			return seq, subtrees
		else:
			return seq,
	
	def parseSequence(self):
		nodes=[]
		self.skipWhiteSpace()
		while True:
			try:
				node = self.parseNode()
			except SGFParseError:
				if self.verbosity > 6:
					print("Error parsing additional node")
				raise
			nodes.append(node)
			self.skipWhiteSpace()
			if self.nextToken != ';':
				break
		return nodes
	
	def parseNode(self):
		if self.nextToken != ';':
			raise SGFParseError(self.pos, ';', self.nextToken, self.context)
		self.pos += 1
		properties = {}
		self.skipWhiteSpace()
		propmatch = self.propid_re.match(self.data, self.pos)
		while propmatch:
			propident = propmatch.group(0)
			self.pos += len(propident)
			valuelist = []
			self.skipWhiteSpace()
			while True:
				try:
					value = self.parsePropValue()
				except SGFParseError:
					if self.verbosity > 7:
						print("Error parsing first node value")
					raise
				valuelist.append(value[1:-1])
				self.skipWhiteSpace()
				if self.nextToken != '[':
					break
			if propident in properties:
				properties[propident].extend(valuelist)
			else:
				properties[propident] = valuelist
			self.skipWhiteSpace()
			propmatch = self.propid_re.match(self.data, self.pos)
		return properties
	
	def parsePropValue(self):
		if self.nextToken != '[':
			raise SGFParseError(self.pos, '[', self.nextToken, self.context)
		value = self.value_re.match(self.data, self.pos)
		if value:
			self.pos += len(value.group(0))
			return value.group(0)
		else:
			self.pos = len(self.data) - 1
			raise SGFParseError(self.pos, ']', self.nextToken, self.context)
