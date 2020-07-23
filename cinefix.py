#!/usr/bin/env python3

import sys
from fractions import Fraction
from numpy import float32

def getInt(f):
	return int.from_bytes(f.read(4), byteorder='big')

def uintBytes(i):
	return i.to_bytes(4, byteorder='big', signed=False)

class SampleRec:
	def commonInit(self):
		if self.time == 0x7FFFFFFF:
			self.type = 'Audio'
		else:
			self.type = 'Video'
		
	def __init__(self, start, size, time, duration):
		self.start = start
		self.size = size
		self.time = time
		self.duration = duration
		self.commonInit()

	def __init__(self, f):
		self.start = getInt(f)
		self.size = getInt(f)
		time = getInt(f)
		self.time = time & 0x7FFFFFFF
		self.shadowSyncSample = time >> 31
		self.duration = getInt(f)
		self.commonInit()

	def isAudio(self):
		if self.time == 0x7FFFFFFF:
			return True
		else:
			return False

	def write(self, f):
		f.write(uintBytes(self.start))
		f.write(uintBytes(self.size))
		f.write(uintBytes(self.time | self.shadowSyncSample << 31))
		f.write(uintBytes(self.duration))

class SampleTable:
	def commonInit(self):
		self.timeUnit = 1.0 / float(self.timescale)
		
	def __init__(self, timescale, sampleRecords):
		self.timescale = timescale
		self.sampleRecords = sampleRecords
		self.commonInit()

	def __init__(self, f):
		hdr = f.read(4)

		if b'STAB' != hdr:
			print("Sample table header not found")
			sys.exit(1)

		hdrSize = getInt(f)

		self.timescale = getInt(f)

		self.commonInit()

		count = getInt(f)

		self.sampleRecords = []

		if hdrSize != 16 + (16 * count):
			print("WARNING: Invalid sample header size detected!")
	
		for sNum in range(count):
			sRec = SampleRec(f)
			self.sampleRecords.append(sRec)

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
	def __init__(self, start, size, time, syncPattern):
		self.start = start
		self.size = size
		self.time = time
		self.syncPattern = syncPattern

	def __init__(self, f):
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
	def __init__(self, timescale, chunkRecords):
		self.timescale = timescale
		self.chunkRecords = chunkRecords
		for cRec in chunkRecords:
			cRec.parent = self

	def __init__(self, f):
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
			cRec = ChunkRec(f)
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
			self.sampleTable = SampleTable(f)
		else:
			self.sampleTable = sampleTable

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
	def commonInit(self, fileOffset, syncPattern):
		self.fileOffset = fileOffset
		self.syncPattern = syncPattern

	def __init__(self, fileOffset, syncPattern, sampleTable):
		SampleContainer.__init__(self, sampleTable=sampleTable)
		self.commonInit(fileOffset, syncPattern)

	def __init__(self, f, fileOffset, syncPattern):
		for i in range(16):
			syncData = getInt(f)
			if syncData != syncPattern:
				print("WARNING: Invalid sync data in chunk!")

		SampleContainer.__init__(self, f=f)

		self.commonInit(fileOffset, syncPattern)

		# Skip past the sample data.
		# Seek to offset of end of last sample from current position
		f.seek(self.sampleTable.sampleRecords[-1].start + self.sampleTable.sampleRecords[-1].size, 1)

	def getDataOffset(self):
		return self.fileOffset + 64 + self.sampleTable.getSize()

	def writeHeader(self, f):
		for i in range(16):
			f.write(uintBytes(self.syncPattern))

		self.sampleTable.write(f)

class FrameDescription:
	def __init__(self, compressionType, width, height):
		self.compressionType = compressionType
		self.width = width
		self.height = height

	def __init__(self, f):
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
	def commonInit(self):
		# This is the NTSC video clock, in Hz.  The PAL one is 26593900.
		# Which is correct when value is baked into a region-agnostic file???
		jagVidClock = 26590906

		# jagSampleRate = (jagVidClock / (2 * (sclk + 1))) / 32
		jagSampleRate = Fraction(jagVidClock, (2 * (self.sclk + 1)) * 32)

		# sampleRate = jagSampleRate + (jagSampleRate / (2^32 / driftRate))
		self.sampleRate = float(jagSampleRate + Fraction(jagSampleRate, Fraction(0xFFFFFFFF, self.driftRate)))
		
	def __init__(self, channels=1, bits=8, compression="uncompressed", signed=0, sclk=0x18, driftRate=0x481db08):
		self.channels = channels
		self.bits = bits
		self.compression = compression
		self.signed = signed
		self.sclk = sclk
		self.driftRate = driftRate

		self.commonInit()

	def __init__(self, f):	
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

		self.commonInit()

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
	def __init__(self, frameDesc, audioDesc, chunkTable, sampleTable=None):
		self.frameDesc = frameDesc
		self.audioDesc = audioDesc
		self.chunkTable = chunkTable
		SampleContainer.__init__(self, sampleTable=sampleTable)

	def __init__(self, f):
		# Read Frame/Film header atom
		hdr = f.read(4)

		if b'FILM' != hdr:
			print("Film header not found")
			sys.exit(1)

		hdrSize = getInt(f)
		# Skip over version and reserved fields
		f.seek(8, 1) # 8 bytes from SEEK_CUR

		self.frameDesc = FrameDescription(f)

		# Peak ahead to see if there is an Audio Description Atom?
		hdr = f.read(4)
		f.seek(-4, 1) # Seek back 4 bytes from SEEK_CUR

		if b'ADSC' == hdr:
			self.audioDesc = AudioDescription(f)
		else:
			self.audioDesc = AudioDescription()

		self.chunks = []

		# Peak ahead to see if this is a chunky or smooth film
		hdr = f.read(4)
		f.seek(-4, 1) # Seek back 4 bytes from SEEK_CUR

		if b'STAB' == hdr:
			# Smooth film
			SampleContainer.__init__(self, f=f)
			self.chunkTable = None
		elif b'CTAB' == hdr:
			# Chunky film
			SampleContainer.__init__(self)
			self.chunkTable = ChunkTable(f)
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

	def getSample(self, f, index, readData):
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

		return Chunk(f, cOffset, cRec.syncPattern)

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
	def __init__(self, film, f):
		self.sampleRate = float32(film.audioDesc.sampleRate)
		self.timescale = float32(film.getTimescale())
		self.vidTime = 0
		self.aNextTime = float32(0)
		self.firstAudioSample = True
		self.sampleIterator = SampleIterator(film, f)

	def setNextAudioSampleTime(self, curSample):
		# XXX assumes 8-bit audio
		sampleDuration = (float32(curSample.size) / self.sampleRate) * self.timescale
		print("Audio sample duration: " + str(sampleDuration))
		if self.firstAudioSample:
			self.aNextTime += float32(sampleDuration) / float32(2.0)
			self.firstAudioSample = False
		else:
			self.aNextTime = float32(sampleDuration) + self.aNextTime

		print("Next audio sample at: " + str(self.aNextTime) + " current vidTime: " + str(self.vidTime))

	def getNextSampleType(self):
		if self.aNextTime < float32(self.vidTime + 1):
			return 'Audio'
		else:
			return 'Video'

	def processSample(self, curSample):
		if curSample.type == 'Audio':
			self.setNextAudioSampleTime(curSample)
		else:
			self.vidTime += curSample.duration

	def printCurrentIndices(self):
		print("  Chunk: " + str(self.sampleIterator.getPreviousChunkIndex()))
		print("  Sample: " + str(self.sampleIterator.getPreviousSampleIndex()))


	def checkSample(self, sampleRec):
		nextSampleType = self.getNextSampleType()

		if nextSampleType == 'Audio':
			if sampleRec.type != 'Audio':
				print("Audio sample not found at expected time!")
				self.printCurrentIndices()
				print("  Vid time: " + str(self.vidTime) + " aNextTime: " + str(self.aNextTime))
				return False

		else:
			if sampleRec.type != 'Video':
				print("Audio sample found before expected time!")
				self.printCurrentIndices()
				print("  Calculated time units remaining: " + str(self.aNextTime - float32(self.vidTime)))
				return False

		return True

	def checkFilm(self):
		for s in self.sampleIterator:
			if not self.checkSample(s.record):
				return False
			self.processSample(s.record)

		return True

with open("ct-1.crg", "rb") as cpkIn:
	film = Film(cpkIn)

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

	with open("ct-1.fixed.crg", "wb") as cpkOut:
		print("Writing new film header")

		film.writeHeader(cpkOut)

		for cIdx in range(len(film.chunkTable.chunkRecords)):
			chunk = film.getChunk(cpkIn, cIdx)
			chunk.writeHeader(cpkOut)
			for sIdx in range(len(chunk.sampleTable.sampleRecords)):
				print("Copying chunk " + str(cIdx) + " sample " + str(sIdx))
				sample = chunk.getSample(cpkIn, sIdx, True)
				cpkOut.write(sample.data)
