#!/usr/bin/env python3

import sys
from fractions import Fraction
from numpy import float32

def getInt(f):
	return int.from_bytes(f.read(4), byteorder='big')

def uintBytes(i):
	return i.to_bytes(4, byteorder='big', signed=False)

def uint16Bytes(i):
	return i.to_bytes(2, byteorder='big', signed=False)

class SampleRec:
	def calcValues(self):
		if self.time == 0x7FFFFFFF:
			self.type = 'Audio'
		else:
			self.type = 'Video'

	def __init__(self, start=None, size=None, time=None, shadowSyncSample=None, duration=None, f=None):
		if f != None:
			self.read(f)
		else:
			self.start = start
			self.size = size
			self.time = time
			self.shadowSyncSample = shadowSyncSample
			self.duration = duration
			self.calcValues()

	def read(self, f):
		self.start = getInt(f)
		self.size = getInt(f)
		time = getInt(f)
		self.time = time & 0x7FFFFFFF
		self.shadowSyncSample = time >> 31
		self.duration = getInt(f)
		self.calcValues()

	def write(self, f):
		f.write(uintBytes(self.start))
		f.write(uintBytes(self.size))
		f.write(uintBytes(self.time | self.shadowSyncSample << 31))
		f.write(uintBytes(self.duration))

	def isAudio(self):
		if self.type == 'Audio':
			return True
		else:
			return False

class SampleTable:
	def calcValues(self):
		self.timeUnit = 1.0 / float(self.timescale)

	def __init__(self, timescale=None, sampleRecords=None, f=None):
		if f != None:
			self.read(f)
		else:
			self.timescale = timescale
			self.sampleRecords = sampleRecords
			self.calcValues()

	def read(self, f):
		hdr = f.read(4)

		if b'STAB' != hdr:
			print("Sample table header not found")
			sys.exit(1)

		hdrSize = getInt(f)

		self.timescale = getInt(f)

		count = getInt(f)

		self.sampleRecords = []

		if hdrSize != 16 + (16 * count):
			print("WARNING: Invalid sample header size detected!")
	
		for sNum in range(count):
			sRec = SampleRec(f=f)
			self.sampleRecords.append(sRec)

		self.calcValues()

	def getSize(self):
		return 16 + len(self.sampleRecords) * 16

	def write(self, f):
		f.write(b'STAB')
		f.write(uintBytes(self.getSize()))
		f.write(uintBytes(self.timescale))
		f.write(uintBytes(len(self.sampleRecords)))
		for sRec in self.sampleRecords:
			sRec.write(f)

class Sample:
	def __init__(self, record, data):
		self.record = record
		self.data = data

class ChunkRec:
	def __init__(self, start=None, size=None, time=None, syncPattern=None, f=None):
		if f != None:
			self.read(f)
		else:
			self.start = start
			self.size = size
			self.time = time
			self.syncPattern = syncPattern

	def read(self, f):
		self.start = getInt(f)
		self.size = getInt(f)
		self.time = getInt(f)
		self.syncPattern = getInt(f)

	def write(self, f):
		f.write(uintBytes(self.start))
		f.write(uintBytes(self.size))
		f.write(uintBytes(self.time))
		f.write(uintBytes(self.syncPattern))

class ChunkTable:
	def __init__(self, timescale=None, chunkRecords=None, f=None):
		if f != None:
			self.read(f)
		else:
			self.timescale = timescale
			self.chunkRecords = chunkRecords
			for cRec in chunkRecords:
				cRec.parent = self

	def read(self, f):
		# XXX temp
		hdr = f.read(4)

		if b'CTAB' != hdr:
			print("Chunk table header not found")
			sys.exit(1)

		size = getInt(f)

		self.timescale = getInt(f)

		print("Timescale: " + str(self.timescale))

		count = getInt(f)

		print("Number of chunks: " + str(count))

		self.chunkRecords = []

		for cNum in range(count):
			cRec = ChunkRec(f=f)
			self.chunkRecords.append(cRec)

	def getSize(self):
		return 16 + len(self.chunkRecords) * 16

	def write(self, f):
		f.write(b'CTAB')
		f.write(uintBytes(self.getSize()))
		f.write(uintBytes(self.timescale))
		f.write(uintBytes(len(self.chunkRecords)))

		for cRec in self.chunkRecords:
			cRec.write(f)

class SampleContainer:
	def __init__(self, sampleTable=None, f=None):
		if f != None:
			self.sampleTable = SampleTable(f=f)
		else:
			self.sampleTable = sampleTable

	def read(self, f):
		self.sampleTable = SampleTable(f=f)

	def getSample(self, f, index, readData=False):
		if index >= len(self.sampleTable.sampleRecords):
			return None

		sRec = self.sampleTable.sampleRecords[index]
		data = None

		if readData:
			# Seek from SEEK_SET to the offset of the sample
			f.seek(self.getDataOffset() + sRec.start, 0)
			data = f.read(sRec.size)

		return Sample(sRec, data)

class Chunk(SampleContainer):
	def __init__(self, fileOffset, syncPattern, sampleTable=None, f=None):
		self.fileOffset = fileOffset
		self.syncPattern = syncPattern

		if f != None:
			self._readHeader(f)
			SampleContainer.__init__(self, f=f)
			self._skipSamples(f)
		else:
			SampleContainer.__init__(self, sampleTable=sampleTable)

	def _readHeader(self, f):
		for i in range(16):
			syncData = getInt(f)
			if syncData != self.syncPattern:
				print("WARNING: Invalid sync data in chunk!")
		
	def _skipSamples(self, f):
		# Skip past the sample data.
		# Seek to offset of end of last sample from current position
		f.seek(self.sampleTable.sampleRecords[-1].start + self.sampleTable.sampleRecords[-1].size, 1)

	def read(self, f):
		self._readHeader(f)
		SampleContainer.read(self, f=f)
		self._skipSamples(f)

	def getDataOffset(self):
		return self.fileOffset + 64 + self.sampleTable.getSize()

	def writeHeader(self, f):
		for i in range(16):
			f.write(uintBytes(self.syncPattern))

		self.sampleTable.write(f)

class FrameDescription:
	def __init__(self, compressionType=None, width=None, height=None, f=None):
		if f != None:
			self.read(f)
		else:
			self.compressionType = compressionType
			self.width = width
			self.height = height

	def read(self, f):
		hdr = f.read(4)

		if b'FDSC' != hdr:
			print("Frame description header not found")
			sys.exit(1)

		size = getInt(f)
	
		if size != 20:
			print("Invalid frame description size: " + str(size))
			sys.exit(1)

		self.compressionType = f.read(4)
		self.height = getInt(f)
		self.width = getInt(f)

	def getSize(self):
		return 20

	def write(self, f):
		f.write(b'FDSC')
		f.write(uintBytes(self.getSize()))
		f.write(self.compressionType)
		f.write(uintBytes(self.height))
		f.write(uintBytes(self.width))

class AudioDescription:
	def calcValues(self):
		# This is the NTSC video clock, in Hz.  The PAL one is 26593900.
		# Which is correct when value is baked into a region-agnostic file???
		jagVidClock = 26590906

		# jagSampleRate = (jagVidClock / (2 * (sclk + 1))) / 32
		jagSampleRate = Fraction(jagVidClock, (2 * (self.sclk + 1)) * 32)

		# sampleRate = jagSampleRate + (jagSampleRate / (2^32 / driftRate))
		self.sampleRate = float(jagSampleRate + Fraction(jagSampleRate, Fraction(0xFFFFFFFF, self.driftRate)))

	def __init__(self, channels=1, bits=8, compression="uncompressed", signed=0, sclk=0x18, driftRate=0x481db08, f=None):
		if f != None:
			self.read(f)
		else:
			self.channels = channels
			self.bits = bits
			self.compression = compression
			self.signed = signed
			self.sclk = sclk
			self.driftRate = driftRate

		self.calcValues()

	def read(self, f):	
		hdr = f.read(4)

		if b'ADSC' != hdr:
			print("Audio description header not found")
			sys.exit(1)

		size = getInt(f)

		if size != 20:
			print("WARNING: Invalid audio description size detected!")
			sys.exit(1)

		audioData = getInt(f)

		self.channels = audioData & 0x1

		if audioData & 0x2:
			self.bits = 16
		else:
			self.bits = 8

		audioCmpr = (audioData >> 2) & 0x3f
		
		if audioCmpr == 0x0:
			self.compression = "uncompressed"
		elif audioCmpr == 0x1:
			self.compression = "n^2 compression"
		else:
			self.compression = "unknown compression"

		self.signed = audioData >> 31

		self.sclk = getInt(f)

		self.driftRate = getInt(f)

		self.calcValues()

	def getSize(self):
		return 20

	def write(self, f):
		f.write(b'ADSC')
		f.write(uintBytes(self.getSize()))

		audioData = self.channels
		if self.bits == 16:
			audioData |= 0x2
		if self.compression == "n^2 compression":
			audioData |= (0x1 << 2)

		audioData |= self.signed << 31

		f.write(uintBytes(audioData))
		f.write(uintBytes(self.sclk))
		f.write(uintBytes(self.driftRate))

class Film(SampleContainer):
	def __init__(self, frameDesc=None, audioDesc=None, chunkTable=None, sampleTable=None, f=None):
		if f != None:
			self._readHeader(f)
			if self.type == 'Smooth':
				SampleContainer.__init__(self, f=f)
				self.chunkTable = None
			elif self.type == 'Chunky':
				SampleContainer.__init__(self, sampleTable=None)
				self.chunkTable = ChunkTable(f=f)
			else:
				print("Neither Sample nor Chunk table found")
				sys.exit(1)
		else:
			self.frameDesc = frameDesc
			self.audioDesc = audioDesc
			self.chunkTable = chunkTable
			SampleContainer.__init__(self, sampleTable=sampleTable)

	def _readHeader(self, f):
		# Read Frame/Film header atom
		hdr = f.read(4)

		if b'FILM' != hdr:
			print("Film header not found")
			sys.exit(1)

		hdrSize = getInt(f)
		# Skip over version and reserved fields
		f.seek(8, 1) # 8 bytes from SEEK_CUR

		self.frameDesc = FrameDescription(f=f)

		# Peak ahead to see if there is an Audio Description Atom?
		hdr = f.read(4)
		f.seek(-4, 1) # Seek back 4 bytes from SEEK_CUR

		if b'ADSC' == hdr:
			self.audioDesc = AudioDescription(f=f)
		else:
			self.audioDesc = AudioDescription()

		self.chunks = []

		# Peak ahead to see if this is a chunky or smooth film
		hdr = f.read(4)
		f.seek(-4, 1) # Seek back 4 bytes from SEEK_CUR

		if b'STAB' == hdr:
			self.type = 'Smooth'
		elif b'CTAB' == hdr:
			self.type = 'Chunky'
		else:
			self.type = None

	def read(self, f):
		self._readHeader(f)

		if self.type == 'Smooth':
			SampleContainer.read(self, f=f)
			chunkTable = None
		elif self.type == 'Chunky':
			SampleContainer.sampleTable = None
			chunkTable = ChunkTable(f=f)
		else:
			print("Neither Sample nor Chunk table found")
			sys.exit(1)

	def getTimescale(self):
		if self.sampleTable != None:
			return self.sampleTable.timescale
		else:
			return self.chunkTable.timescale

	def getDataOffset(self):
		offset = 16 + self.frameDesc.getSize() + self.audioDesc.getSize()
		if self.sampleTable != None:
			offset += self.sampleTable.getSize()
		else:
			offset += self.chunkTable.getSize()

		return offset

	def writeHeader(self, f):
		# Write the Frame/Film header atom
		f.write(b'FILM')

		size = self.getDataOffset()
		f.write(uintBytes(size))

		f.write(uintBytes(0)) # Version
		f.write(uintBytes(0)) # Reserved

		self.frameDesc.write(f)
		self.audioDesc.write(f)

		if self.sampleTable != None:
			self.sampleTable.write(f)
		else:
			self.chunkTable.write(f)

	def getSample(self, f, index, readData=False):
		if self.sampleTable == None:
			return None

		return SampleContainer.getSample(self, f, index, readData)

	def getChunk(self, f, index):
		if self.chunkTable == None:
			return None

		if index >= len(self.chunkTable.chunkRecords):
			return None

		cRec = self.chunkTable.chunkRecords[index]
		cOffset = self.getDataOffset() + cRec.start

		f.seek(cOffset, 0) # Seek cOffset bytes from SEEK_SET

		return Chunk(cOffset, cRec.syncPattern, f=f)

	def isChunky(self):
		return (self.type == 'Chunky')

class SampleIterator:
	def __init__(self, film, f, readSampleData=False):
		self.film = film
		self.f = f
		self.readSampleData = readSampleData
		self.currentChunkIndex = 0
		self.currentSampleIndex = 0
		self.currentChunk = None

	def __iter__(self):
		self.currentChunkIndex = 0
		self.currentSampleIndex = 0
		self.currentChunk = film.getChunk(self.f, self.currentChunkIndex)

		# Don't bother handling non-existant corner case of empty chunk

		return self

	def __next__(self):
		if self.film.sampleTable == None:
			if self.currentChunk == None:
				raise StopIteration

			# Return Sample at currentSampleIndex
			s = self.currentChunk.getSample(self.f, self.currentSampleIndex, self.readSampleData)

			# Find next sample
			self.currentSampleIndex += 1
			if self.currentSampleIndex >= len(self.currentChunk.sampleTable.sampleRecords):
				self.currentSampleIndex = 0
				self.currentChunkIndex += 1
				self.currentChunk = film.getChunk(self.f, self.currentChunkIndex)
		else:
			s = film.getSample(self.f, self.currentSampleIndex, self.readSampleData)

			if s == None:
				raise StopIteration

			self.currentSampleIndex += 1

		return s

	def getPreviousChunkIndex(self):
		if self.film.sampleTable != None:
			return None

		if self.currentSampleIndex == 0:
			return self.currentChunkIndex - 1
		else:
			return self.currentChunkIndex

	def getPreviousSampleIndex(self):
		if self.film.sampleTable != None:
			return self.currentSampleIndex - 1

		if self.currentSampleIndex == 0:
			return len(self.film.getChunk(self.f, self.currentChunkIndex - 1).sampleTable.sampleRecords) - 1
		else:
			return self.currentSampleIndex - 1

class AudioSampleIterator(SampleIterator):
	def __next__(self):
		s = SampleIterator.__next__(self)

		while s.record.type != 'Audio':
			s = SampleIterator.__next__(self)

		return s

class VideoSampleIterator(SampleIterator):
	def __next__(self):
		s = SampleIterator.__next__(self)

		while s.record.type != 'Video':
			s = SampleIterator.__next__(self)

		return s

class VidState:
	def reset(self):
		self.vidTime = 0
		self.aNextTime = float32(0)
		self.firstAudioSample = True

	def __init__(self, film, f):
		self.sampleRate = float32(film.audioDesc.sampleRate)
		self.timescale = float32(film.getTimescale())
		self.film = film
		self.file = f
		if self.film.isChunky():
			# Handle one-chunk films :-(
			self.chunkDuration = self.film.chunkTable.chunkRecords[1].time - self.film.chunkTable.chunkRecords[0].time

	def setNextAudioSampleTime(self, curSample):
		# XXX assumes 8-bit audio
		sampleDuration = (float32(curSample.size) / self.sampleRate) * self.timescale
		#print("Audio sample duration: " + str(sampleDuration))
		if self.firstAudioSample:
			self.aNextTime += float32(sampleDuration) / float32(2.0)
			self.firstAudioSample = False
		else:
			self.aNextTime = float32(sampleDuration) + self.aNextTime

		#print("Next audio sample at: " + str(self.aNextTime) + " current vidTime: " + str(self.vidTime))

	def calcNextSampleType(self):
		if self.aNextTime < float32(self.vidTime + 1):
			return 'Audio'
		else:
			return 'Video'

	def processSample(self, curSample):
		if curSample.type == 'Audio':
			self.setNextAudioSampleTime(curSample)
		else:
			self.vidTime += curSample.duration

	def printCurrentIndices(self, sampleIterator):
		print("  Chunk: " + str(sampleIterator.getPreviousChunkIndex()))
		print("  Sample: " + str(sampleIterator.getPreviousSampleIndex()))


	def checkSample(self, sampleRec, sampleIterator):
		nextSampleType = self.calcNextSampleType()

		if nextSampleType == 'Audio':
			if sampleRec.type != 'Audio':
				print("Audio sample not found at expected time!")
				self.printCurrentIndices(sampleIterator)
				print("  Vid time: " + str(self.vidTime) + " aNextTime: " + str(self.aNextTime))
				return False

		else:
			if sampleRec.type != 'Video':
				print("Audio sample found before expected time!")
				self.printCurrentIndices(sampleIterator)
				print("  Calculated time units remaining: " + str(self.aNextTime - float32(self.vidTime)))
				return False

		return True

	def checkFilm(self):
		self.reset()
		sampleIterator = SampleIterator(self.film, self.file)
		for s in sampleIterator:
			if not self.checkSample(s.record, sampleIterator):
				return False
			self.processSample(s.record)

		return True

	def getFixedChunkTable(self):
		self.reset()

		asi = AudioSampleIterator(self.film, self.file).__iter__()
		vsi = VideoSampleIterator(self.film, self.file).__iter__()

		newChunks = []
		# XXX Write a syncPatten "forever" iterator
		# Init size to size of sync pattern + empty sample table
		curRec = ChunkRec(start=0, size=64+16, time=0, syncPattern=0x20202020)
		curChunkDuration = 0
		done = False

		while not done:
			nextType = self.calcNextSampleType()

			sample = None
			if nextType == 'Audio':
				try:
					sample = next(asi)
				except StopIteration:
					# This is normal.  Audio is pre-buffered
					# in the stream to ensure the audio
					# buffer in the player doesn't empty, so
					# we will always run out of audio
					# samples near the end of the stream
					# even when interleaving them correctly.
					pass
			if sample == None:
				try:
					sample = next(vsi)
				except StopIteration:
					# Due to the note above about audio
					# samples being pre-buffered, it is safe
					# to assume running out of video samples
					# means we've reached the end of the
					# stream.
					done = True

				if sample != None:
					curChunkDuration += sample.record.duration
				else:
					# Assert done == True
					pass

			if sample != None:
				# Add in the size of the sample
				curRec.size += sample.record.size
				# Add in the size of a sample record
				curRec.size += 16
			else:
				# Assert done == True
				pass

			if curChunkDuration >= self.chunkDuration or done:
				print("Adding fixed chunk rec #" + str(len(newChunks)) + " from " + str(curRec.time) + " to " + str(curRec.time + curChunkDuration) + " of size " + hex(curRec.size))
				newChunks.append(curRec)
				newStart = curRec.start + curRec.size
				newTime = curRec.time + curChunkDuration
				newPattern = curRec.syncPattern + 0x01010101
				if newPattern >= 0x80808080:
					newPattern = 0x20202020
				# Initi size to size of sync pattern+empty sample table
				curRec = ChunkRec(start=newStart, size=64+16, time=newTime, syncPattern=newPattern)
				curChunkDuration = 0

			if sample != None:
				self.processSample(sample.record)
			else:
				# Assert done == True
				pass

		return ChunkTable(timescale=self.film.getTimescale(), chunkRecords=newChunks)

	def writeFixedData(self, fixedFilm, f):
		self.reset()

		asi = AudioSampleIterator(self.film, self.file, readSampleData=True).__iter__()
		vsi = VideoSampleIterator(self.film, self.file, readSampleData=True).__iter__()

		for cRec in fixedFilm.chunkTable.chunkRecords:
			newSamples = []
			newSampleRecs = []
			# Init size to size of sync pattern + empty sync table
			chunkHdrSize = 64 + 16
			chunkDataSize = 0

			while chunkDataSize < cRec.size - chunkHdrSize:
				nextType = self.calcNextSampleType()

				sample = None
				if nextType == 'Audio':
					try:
						sample = next(asi)
					except StopIteration:
						pass

				if sample == None:
					try:
						sample = next(vsi)
					except StopIteration:
						print("Ran out of video samples while writing sample data")
						sys.exit(1)

				if sample.record.isAudio():
					newTime = sample.record.time
				else:
					newTime = self.vidTime

				newSampleRec = SampleRec(start=chunkDataSize, size=sample.record.size, time=newTime, shadowSyncSample=sample.record.shadowSyncSample, duration=sample.record.duration)
				newSampleRecs.append(newSampleRec)
				# Add in sample data size
				chunkDataSize += newSampleRec.size
				# Add in sample record size
				chunkHdrSize += 16
				newSamples.append(Sample(newSampleRec, sample.data))

				self.processSample(sample.record)

			newSampleTable = SampleTable(timescale=self.film.getTimescale(), sampleRecords=newSampleRecs)
			chunk = Chunk(fileOffset=cRec.start, syncPattern=cRec.syncPattern, sampleTable=newSampleTable)
			chunk.writeHeader(f)
			for s in newSamples:
				f.write(s.data)

with open("ct-1.crg", "rb") as cpkIn:
	film = Film(f=cpkIn)

	cType = film.frameDesc.compressionType

	if cType == b'cvid':
		print("Processed Cinepak compressed-RGB movie")
	elif cType == b'$CRY':
		print("Processed Cinepak expanded-CRY movie")
	elif cType == b'$RGB':
		print("Processed Cinepak expanded-RGB movie")
	else:
		print("Unknown Cinepak compression type!")
		sys.exit(1)

	print("Resolution: " + str(film.frameDesc.width) + "x" + str(film.frameDesc.height))

	if film.audioDesc.bits == 8:
		bits = "8-bit"
	else:
		bits = "16-bit"

	if film.audioDesc.signed == 1:
		signed = "signed"
	else:
		signed = "unsigned"

	if film.audioDesc.channels == 2:
		channels = "stereo"
	else:
		channels = "mono"

	print(bits + " " + signed + " " + channels + " (" + film.audioDesc.compression + ") Audio")
	print("Audio SCLK: " + str(film.audioDesc.sclk))
	print("Audio drift rate: " + str(film.audioDesc.driftRate))
	print("Audio sample rate: " + str(film.audioDesc.sampleRate))

	if film.chunkTable == None:
		print("Smooth file")
	else:
		print("Chunky file")

		vs = VidState(film, cpkIn)
		vs.checkFilm()

	with open("ct-1f.crg", "wb") as cpkOut:
		print("Writing new film header")

		# First create a new sample or chunk table
		vs = VidState(film, cpkIn)
		if film.isChunky():
			fixedSampleTable = None
			fixedChunkTable = vs.getFixedChunkTable()
		else:
			fixedSampleTable = vs.getFixedSampleTable()
			fixedChunkTable = None

		fixedFilm = Film(frameDesc=film.frameDesc, audioDesc=film.audioDesc, chunkTable=fixedChunkTable, sampleTable=fixedSampleTable)
		fixedFilm.writeHeader(cpkOut)

		vs.writeFixedData(fixedFilm, cpkOut)

# Wrap the fixed file in a dummy AIFF header and (obsolete) sync marker padding
# Details on the AIFF file format are available here:
#   http://www-mmsp.ece.mcgill.ca/Documents/AudioFormats/AIFF/Docs/AIFF-1.3.pdf
with open("ct-1f.crg", "rb") as cpkIn, open("ct-1f.aif", "wb") as aifOut:
	cpkIn.seek(0, 2) # Seek to 0 bytes from SEEK_END
	cpkSize = cpkIn.tell()
	cpkIn.seek(0, 0) # Seek to 0 bytes from SEEK_SET

	# 24 x 2352 (CD block size) blocks of 'A'.  Note JagCinePak uses 0xdc82
	# instead, and the Jaguar Cinepak documentation suggests 0xdc7e is used,
	# but 0xdc80 matches the cpkdemo player.inc values the Jaguar Cinepak
	# documentation refers to, and makes a lot more sense
	leaderSize = 0xdc80 # 24 x 2352 byte blocks of 'A'

	# 64 bytes of '1'.  Note JagCinePak doesn't include this in its AIFF
	# size fields
	syncDataSize = 0x40 # 64 bytes of '1'

	# 22146 bytes (Unknown reason for this size) of 'B' This is not
	# documented anywhere I can find, and I see no reason for it, but
	# including it to match JagCinePak.
	trailerSize = 0x5682

	# AIFF Common chunk size:
	commonSize = 0x12

	# AIFF Sound metadata size:
	soundMetaSize = 0x8

	# soundData field size
	soundDataSize = cpkSize + leaderSize + syncDataSize + trailerSize

	# chunk size of sound block
	soundSize = soundDataSize + soundMetaSize

	# formType + common chunk header + sound chunk header + data
	formSize = 0x4 + 0x8 + 0x8 + commonSize + soundSize

	# Write the FORM chunk header
	aifOut.write(b'FORM')
	aifOut.write(uintBytes(formSize))
	aifOut.write(b'AIFF')

	# Write the common chunk
	#
	# The actual values here don't really matter, but are chosen to look
	# like a valid audio file the same size as the film with its padding.
	# JagCinePak tries to use this scheme I think:
	#   channels = 2 (Stereo)
	#   numSampleFrames = <size of "sound" data, film + padding
	#   sampleSize = 16 bits
	#   sampleRate = 44100Hz in Apple's 80-bit floating point format
	# However, this results in non-sensical data.  sampleSize, rounded up to
	# the nearest byte, times channels should equal numSampleFrames.  Hence,
	# to keep things simple but sensible, I've used channels = 1 and
	# sampleSize = 8 instead.  This won't trick any CD burning software into
	# thinking the data is CD-compatible, but other AIFF parsers might
	# handle it better.
	#
	# See this document for more info on Apple's weird "extended" floating
	# point format:
	#
	#   https://vintageapple.org/inside_o/pdf/Apple_Numerics_Manual_Second_Edition_1988.pdf
	#
	# But note it is the same as x87 80-bit floating point, and
	# documentation for that is more readily available.
	aifOut.write(b'COMM')
	aifOut.write(uintBytes(commonSize))
	# Channels
	aifOut.write(uint16Bytes(2))
	# Sample Frames
	aifOut.write(uintBytes(soundDataSize))
	# Sample size
	aifOut.write(uint16Bytes(8))
	# Sample rate:
	#  sign=0 (positive)
	#  exponent=15 (0x400e - 0x3fff)
	#  i=1 (normalized)
	#  fraction=0x2c44000000000000
	#  Packed we get 0x400eac44000000000000, broken into 5 words
	aifOut.write(uint16Bytes(0x400e))
	aifOut.write(uint16Bytes(0xac44))
	aifOut.write(uint16Bytes(0x0000))
	aifOut.write(uint16Bytes(0x0000))
	aifOut.write(uint16Bytes(0x0000))

	# Write the sound chunk
	aifOut.write(b'SSND')
	aifOut.write(uintBytes(soundSize))

	# offset
	aifOut.write(uintBytes(0))

	# blockSize
	aifOut.write(uintBytes(0))

	# Write the "sound" data:
	for i in range(leaderSize >> 2):
		aifOut.write(b'AAAA')

	for i in range(syncDataSize >> 2):
		aifOut.write(b'1111')

	while True:
		buf = cpkIn.read(0x1000)

		if buf:
			aifOut.write(buf)
		else:
			break

	for i in range(trailerSize >> 1):
		aifOut.write(b'BB')
