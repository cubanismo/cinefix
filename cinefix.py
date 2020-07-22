#!/usr/bin/env python3

import sys
from fractions import Fraction
from numpy import float32

def getInt(f):
	return(int.from_bytes(f.read(4), byteorder='big'))

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
		self.time = getInt(f) & 0x7FFFFFFF
		self.duration = getInt(f)
		self.commonInit()

	def isAudio(self):
		if self.time == 0x7FFFFFFF:
			return True
		else:
			return False

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

class ChunkTable:
	def __init__(self, timescale, chunkRecords):
		self.timescale = timescale
		self.chunkRecords = chunkRecords

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

class Chunk:
	def __init__(self, syncPattern, sampleTable, samples=[]):
		self.syncPattern = syncPattern
		self.sampleTable = sampleTable
		self.samples = samples

	def __init__(self, f, syncPattern, readSamples=False):
		for i in range(16):
			syncData = getInt(f)
			if syncData != syncPattern:
				print("WARNING: Invalid sync data in chunk!")

		self.sampleTable = SampleTable(f)

		self.samples = []
		if readSamples:
			for s in self.sampleTable.sampleRecords:
				sampleData = f.read(s.size)
				self.samples.append(sampleData)
		else:
			# Just skip past the sample data.
			# Seek to offset of end of last sample from current position
			f.seek(self.sampleTable.sampleRecords[-1].start + self.sampleTable.sampleRecords[-1].size, 1)

class VidState:
	def __init__(self, sampleRate, chunkNumber=0, vidTime=0, aNextTime=float32(0), firstAudioSample=True):
		self.sampleRate = float32(sampleRate)
		self.chunkNumber = chunkNumber
		self.vidTime = vidTime
		self.aNextTime = aNextTime
		self.firstAudioSample = firstAudioSample

	def setNextAudioSampleTime(self, curSample, timescale):
		# XXX assumes 8-bit audio
		sampleDuration = (float32(curSample.size) / self.sampleRate) * float32(timescale)
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

	def processSample(self, curSample, timescale):
		if curSample.type == 'Audio':
			self.setNextAudioSampleTime(curSample, timescale)
		else:
			self.vidTime += curSample.duration

	def checkSample(self, sampleRec, timescale):
		nextSampleType = self.getNextSampleType()

		if nextSampleType == 'Audio':
			if sampleRec.type != 'Audio':
				print("Audio sample not found at expected time!")
				print("  Vid time: " + str(self.vidTime) + " aNextTime: " + str(self.aNextTime))
				sys.exit(1)

		else:
			if sampleRec.type != 'Video':
				print("Audio sample found before expected time!")
				print("  Calculated time units remaining: " + str(self.aNextTime - float32(self.vidTime)))
				sys.exit(1)

	def checkChunk(self, cRec):
		for sampleRec in cRec.sampleTable.sampleRecords:
			self.checkSample(sampleRec, cRec.sampleTable.timescale)
			self.processSample(sampleRec, cRec.sampleTable.timescale)
		self.chunkNumber += 1

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

class Film:
	def __init__(self, frameDesc, audioDesc, chunkTable, sampleTable=None):
		self.frameDesc = frameDesc
		self.audioDesc = audioDesc
		self.chunkTable = chunkTable
		self.sampleTable = sampleTable

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
			self.sampleTable = SampleTable(f)
			self.chunkTable = None
		elif b'CTAB' == hdr:
			# Chunky film
			self.sampleTablel = None
			self.chunkTable = ChunkTable(f)
			# Read the chunk sample tables, but skip their samples.
			for cRec in self.chunkTable.chunkRecords:
				self.chunks.append(Chunk(f, cRec.syncPattern))
		else:
			print("Neither Sample nor Chunk table found")
			sys.exit(1)

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

		vs = VidState(film.audioDesc.sampleRate)

		for cRec in film.chunkTable.chunkRecords:
			print("Checking chunk #" + str(vs.chunkNumber) + ":")

			print("At chunk start, Vid time: " + str(vs.vidTime) + " next audio sample time: " + str(vs.aNextTime))
			vs.checkChunk(film.chunks[vs.chunkNumber])
