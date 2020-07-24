Jaguar Cinepak Audio Fixing Tool
================================

[JagMod's Jaguar Cinepak Tool][1]'s output files seem to have corrupted audio
after some point in the file.  This tool rebuilds the chunk and sample tables,
placing the audio samples in the correct locations, thereby fixing the
audio corruption, and often preventing the Jaguar Cinepak player from
crashing at around this point in the file as well.

The tool outputs a fixed .crg file, and optionally a version of the file
with an AIFF header and the "leader" padding expected by cpkdemo, as well
as a ready-to-burn raw Jaguar track file.

Requirements
------------

* Python 3.2+
* NumPy (For float32 math)

On Ubuntu or Window Subsystem for Linux 2/WSL2, you can get them like this:

    $ sudo apt install python3 python3-numpy

How to use it
-------------

    usage: cinefix.py [-h] -o FIXED_FILE [-a FIXED_AIFF_FILE]
                      [-t FIXED_TRACK_FILE] [-n TRACK_NUMBER] [-z]
                      INPUT_FILE
    
    positional arguments:
      INPUT_FILE            Chunk cinepak file
    
    optional arguments:
      -h, --help            show this help message and exit

      -o FIXED_FILE, --fixed-file FIXED_FILE
                            Name of file to store the output in

      -a FIXED_AIFF_FILE, --fixed-aiff-file FIXED_AIFF_FILE
                            Name of file to store the fixed cinepak data in with
                            an AIFF wrapper. If not specified, no AIFF file is
                            generated

      -t FIXED_TRACK_FILE, --fixed-track-file FIXED_TRACK_FILE
                            Name of a track file to store the fixed cinepak data
                            in with an AIFF and track wrapper in. If not
                            specified, no track file is generated.

      -n TRACK_NUMBER, --track-number TRACK_NUMBER
                            Track number to embed in the generated track file

      -z, --leading-zero-word
                            Write a dummy ZERO word at the start of the track file

Examples
--------

    # Fix a chunky file, outputting only a new chunky file:
    $ ./cinefix.py ../badfiles/movie.crg -o movie.crg

    # Fix a chunky file, also outputting an AIFF-wrapped fixed file:
    $ ./cinefix.py ../badfiles/movie.crg -o movie.crg -a movie.aif

    # Fix a chunky file, also outputting an AIFF-wrapped fixed file
    # and a raw Jaguar track file that will be used as the 2nd data
    # track on the data session of a Jaguar CD disk, adding a leading
    # zero word (needed with cdrecord, among others) to properly align
    # the track on disk:
    $ ./cinefix.py ../badfiles/movie.crg -o movie.crg -a movie.aif \
          -n 1 -z -t movie.t01

[1]: http://www.jagmod.com
