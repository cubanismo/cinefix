#!/usr/bin/env python3

import sys
from fractions import Fraction
from numpy import float32

def getInt(f):
	return(int.from_bytes(f.read(4), byteorder='big'))

class SampleRec:
	def __init__(self, start, size, time, duration):
		self.start = start
		self.size = size
		self.time = time
		self.duration = duration

		if self.time == 0x7FFFFFFF:
			self.type = 'Audio'
		else:
			self.type = 'Video'

class SampleHdr:
	def __init__(self, timescale, sampleRecords):
		self.timescale = timescale
		self.timeUnit = 1.0 / float(timescale)
		self.sampleRecords = sampleRecords

class ChunkRec:
	def __init__(self, sampleHeader, samples=[]):
		self.sampleHeader = sampleHeader
		self.samples = samples

def processSampleHdr(f):
	sHdr = f.read(4)

	if b'STAB' != sHdr:
		print("Sample table header not found")
		sys.exit(1)

	sHdrSize = getInt(f)

	sTimescale = getInt(f)

	print("Sample timescale: " + str(sTimescale))

	sTimeUnit = 1.0 / float(sTimescale)

	sCount = getInt(f)

	sRecs = []

	for sNum in range(sCount):
		sStart = getInt(f)
		sSize = getInt(f)
		sTime = getInt(f) & 0x7FFFFFFF
		sDuration = getInt(f)

		sRecs.append(SampleRec(sStart, sSize, sTime, sDuration))

		if sTime == 0x7FFFFFFF:
			print("Processed Audio sample record")
		else:
			print("Processed Video sample record at " + "{:.5f}".format(sTime * sTimeUnit) + "-" + "{:.5f}".format((sTime + sDuration) * sTimeUnit))

	return SampleHdr(sTimescale, sRecs)

def processChunk(f, readSamples=False):
	# Skip chunk sync marker for now
	f.seek(64, 1) # Seek 64 bytes from SEEK_CUR

	sHdr = processSampleHdr(f)

	if readSamples:
		samples = []

		for s in sHdr.sampleRecords:
			sampleData = f.read(s.size)
			samples.append(sampleData)

		return ChunkRec(sHdr, samples)
	else:
		# Just skip past the sample data.
		# Seek to offset of end of last sample from current position
		f.seek(sHdr.sampleRecords[-1].start + sHdr.sampleRecords[-1].size, 1)

		return ChunkRec(sHdr)

class VidState:
	def __init__(self, sampleRate, vidTime=0, aNextTime=float32(0), firstSample=True):
		self.sampleRate = float32(sampleRate)
		self.vidTime = vidTime
		self.aNextTime = aNextTime
		self.firstSample = firstSample

def checkChunk(cRec, vs):
	for sampleRec in cRec.sampleHeader.sampleRecords:
		if vs.aNextTime < float32(vs.vidTime + 1):
			if sampleRec.type != 'Audio':
				print("Audio sample not found at expected time!")
				print("  Vid time: " + str(vs.vidTime) + " aNextTime: " + str(vs.aNextTime))
				sys.exit(1)
			else:
				# XXX assumes 8-bit audio
				sampleDuration = (float32(sampleRec.size) / vs.sampleRate) * float32(cRec.sampleHeader.timescale)
				print("Audio sample duration: " + str(sampleDuration))
				if vs.firstSample:
					vs.aNextTime = (float32(sampleDuration) / float32(2.0)) + vs.aNextTime
					vs.firstSample = False
				else:
					vs.aNextTime = float32(sampleDuration) + vs.aNextTime

				print("New tNext: " + str(vs.aNextTime) + " current vidTime: " + str(vs.vidTime))
		else:
			if sampleRec.type != 'Video':
				print("Audio sample found before expected time!")
				print("  Calculated time units remaining: " + str(vs.aNextTime - float32(vs.vidTime)))
				sys.exit(1)
			else:
				vs.vidTime += sampleRec.duration

with open("ct-1.crg", "rb") as cpkIn:
	# Read Frame/Film header atom
	hdr = cpkIn.read(4)

	if b'FILM' != hdr:
		print("Film header not found")
		sys.exit(1)

	hdrSize = getInt(cpkIn)
	# Skip over version and reserved fields
	cpkIn.seek(8, 1) # 8 bytes from SEEK_CUR

	# Read Frame Description atom
	hdr = cpkIn.read(4)

	if b'FDSC' != hdr:
		print("Frame description not found")
		sys.exit(1)

	fdscSize = getInt(cpkIn)
	
	if fdscSize != 20:
		print("Invalid frame description size")
		sys.exit(1)

	cType = cpkIn.read(4)

	if cType == b'cvid':
		print("Processing Cinepak compressed-RGB movie")
	elif cType == b'$CRY':
		print("Processing Cinepak expanded-CRY movie")
	elif cType == b'$RGB':
		print("Processing Cinepak expanded-RGB movie")
	else:
		print("Unknown Cinepak compression type!")
		sys.exit(1)

	height = getInt(cpkIn)
	width = getInt(cpkIn)

	print("Resolution: " + str(width) + "x" + str(height))

	# Is there an Audio Description Atom?
	hdr = cpkIn.read(4)

	if b'ADSC' == hdr:
		adscSize = getInt(cpkIn)

		if adscSize != 20:
			print("Invalid audio description size")
			sys.exit(1)

		audioData = getInt(cpkIn)

		if audioData & 0x1:
			channels = "Stereo"
		else:
			channels = "Mono"

		if audioData & 0x2:
			bits = "16-bit"
		else:
			bits = "8-bit"

		audioCmpr = (audioData >> 2) & 0x3f
		
		if audioCmpr == 0x0:
			compression = "uncompressed"
		elif audioCmpr == 0x1:
			compression = "n^2 compression"
		else:
			compression = "unknown compression"

		if audioCmpr & 0x80000000:
			signed = "signed"
		else:
			signed = "unsigned"

		print(bits + " " + signed + " " + channels + " (" + compression + ") Audio")

		sclk = getInt(cpkIn)

		print("Audio SCLK: " + str(sclk))

		driftRate = getInt(cpkIn)

		print("Audio drift rate: " + str(driftRate))

		# This is the NTSC video clock, in Hz.  The PAL one is 26593900.
		# Which is correct when value is baked into a region-agnostic file???
		jagVidClock = 26590906

		# jagSampleRate = (jagVidClock / (2 * (sclk + 1))) / 32
		jagSampleRate = Fraction(jagVidClock, (2 * (sclk + 1)) * 32)

		# sampleRate = jagSampleRate + (jagSampleRate / (2^32 / driftRate))
		sampleRate = float(jagSampleRate + Fraction(jagSampleRate, Fraction(0xFFFFFFFF, driftRate)))

		print("Audio sample rate: " + str(sampleRate))

		# Read next header (Chunk table or Sample table)
		hdr = cpkIn.read(4)
	else:
		print("No Audio Descriptor Atom")
		sampleRate = 22050.0


	if b'STAB' == hdr:
		print("Smooth file")

		processSampleHdr(cpkIn)
	elif b'CTAB' == hdr:
		print("Chunky file")

		ctabSize = getInt(cpkIn)

		timescale = getInt(cpkIn)

		print("Timescale: " + str(timescale))

		chunkCount = getInt(cpkIn)

		print("Number of chunks: " + str(chunkCount))

		# Skip past chunk records for now
		cpkIn.seek(chunkCount * 16, 1) # Seek chunkCount * 16 from SEEK_CUR

		vs = VidState(sampleRate)

		for cNum in range(chunkCount):
			print("Processing chunk #" + str(cNum) + ":")
			cRec = processChunk(cpkIn)

			print("At chunk start, Vid time: " + str(vs.vidTime) + " next audio sample time: " + str(vs.aNextTime))
			checkChunk(cRec, vs)
			firstChunk = False
	else:
		print("No sample or chunk table found!")
