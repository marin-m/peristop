#!/usr/bin/python3
#-*- encoding: Utf-8 -*-
from collections import OrderedDict
from struct import unpack
from io import BytesIO
from uuid import UUID

"""
    In video streams, Periscope stores roughly the same metadata (which
    includes frames timestamp and orientation) in two different ways:
    
    - ID3 data, as exploited by the Flash-based player (which happens to
      be dropped when you convert *.ts to .mp4).
    
    - AMF0 data, embedded directy in H.264 data as SEI NAL frames, as
      exploited by mobile applications.
    
    This class takes a broadcast ID and parses the relevant MP4 file in
    order to extract metadata from the second option.
"""

#ffmpeg -y -i ~/peri/storage/live/1jMJglnmwojxL.mp4 -vcodec copy -vbsf h264_mp4toannexb -an /tmp/kek.h264

#MP4 does not use AnnexB. Hence no start codes. The first 4 bytes of each NALU is the size of the NALU in big endian format.

class H264Reader:
    nal_sei = UUID('62100F9A-A411-4E11-9141-482A1368BFD3').bytes
    timescale = None
    
    def __init__(self, bcst):
        self.meta = {'timestamps': [], 'orientations': []}
        
        with open('storage/live/%s.mp4' % bcst, 'rb') as fd:
            self.fd = fd
            self.read_atoms(fd)

    def read_atoms(self, buf):
        chunkOffts = []
        chunkToNbSamples = OrderedDict()
        sampleSizes = []
        sampleToTime = [0]
        syncSamplesIndexes = []
        
        # Iterate through the .mp4 hierarchy
        while True:
            # Atom header
            atom_len = buf.read(4)
            if not atom_len:
                break
            atom_len = unpack('>I', atom_len)[0]
            atom_type = buf.read(4).decode('ascii')
            
            if not atom_len - 8:
                continue
            
            atom = BytesIO(buf.read(atom_len - 8))
            
            # Fullbox header
            if atom_type in ('mdhd', 'stco', 'stsz', 'stsc', 'stss', 'stts'):
                versions, flags = ord(atom.read(1)), int.from_bytes(atom.read(3), 'big')
            
            # Metadata atoms
            if atom_type == 'tkhd':
                if not any(atom.read()[-8:]):
                    return # not video
            elif atom_type == 'mdhd':
                _, _, self.timescale, duration = unpack('>4I', atom.read(16))

            # Chunk info atoms
            elif atom_type == 'stco':
                nb = unpack('>I', atom.read(4))[0]
                chunkOffts = unpack('>%dI' % nb, atom.read(nb * 4))
            elif atom_type == 'stsz':
                _, nb = unpack('>2I', atom.read(8))
                sampleSizes = list(unpack('>%dI' % nb, atom.read(nb * 4)))
            elif atom_type == 'stsc':
                nb = unpack('>I', atom.read(4))[0]
                for i in range(nb):
                    firstChunk, samplesNb, descrNb = unpack('>3I', atom.read(12))
                    chunkToNbSamples[firstChunk - 1] = samplesNb
            elif atom_type == 'stss':
                nb = unpack('>I', atom.read(4))[0]
                syncSamplesIndexes = unpack('>%dI' % nb, atom.read(nb * 4))
            elif atom_type == 'stts':
                nb = unpack('>I', atom.read(4))[0]
                for i in range(nb):
                    nbSamples, timeNb = unpack('>2I', atom.read(8))
                    for j in range(nbSamples):
                        sampleToTime.append(timeNb + sampleToTime[-1])
            
            elif atom_type in ('moov', 'trak', 'mdia', 'minf', 'stbl'):
                self.read_atoms(atom)
        
        # Iterating through chunks
        if chunkOffts:
            timeToNtp = OrderedDict()
            origPos = self.fd.tell()
            sample = 0
            prevTime, prevNtp, prevOrient = None, None, None
            
            for chunk, nbSamples in chunkToNbSamples.items():
                while True:
                    self.fd.seek(chunkOffts[chunk])
                    
                    # Iterating through samples
                    for i in range(nbSamples):
                        if sample + 1 in syncSamplesIndexes:
                            amf = self.read_H264(BytesIO(self.fd.read(sampleSizes[sample]).replace(b'\0\0\3', b'\0\0')))
                            
                            lastTime = sampleToTime[sample] / self.timescale # Wait isn't this the next??
                            lastNtp = amf['ntp'] - 2208988800
                            
                            if not prevNtp or (lastNtp - lastTime) - (prevNtp - prevTime) >= 0.5:
                                self.meta['timestamps'].append([lastTime, lastNtp])
                                #print(lastTime, '=', lastNtp)
                                #if prevNtp:
                                #    print(' (jump: %s)' % ((lastNtp - lastTime) - (prevNtp - prevTime)))
                                
                                prevTime, prevNtp = lastTime, lastNtp
                            
                            lastOrient = int((int(amf['rotation']) + 45) / 90) * 90 % 360
                            lastOrient = -90 if lastOrient == 270 else lastOrient
                            
                            if prevOrient is None or lastOrient != prevOrient:
                                self.meta['orientations'].append([lastTime, lastOrient])
                                #print('\n>>>[Rotate]', lastOrient, '\n')
                                
                                prevOrient = lastOrient
                        else:
                            self.fd.seek(sampleSizes[sample], 1)
                        sample += 1
                    
                    chunk += 1
                    if chunk in chunkToNbSamples.keys() or chunk >= len(chunkOffts):
                        break
            
            self.fd.seek(origPos)

    def read_H264(self, buf):
        while True:
            nal_size = unpack('>I', buf.read(4))[0]
            nal = BytesIO(buf.read(nal_size))
            
            nal_type = ord(nal.read(1)) & 0b11111
            
            if nal_type == 6: # SEI - Supplemental enhancement information
                sei_type, sei_size = self.read_0xff(nal), self.read_0xff(nal)
                sei = BytesIO(nal.read(sei_size))
                
                if sei_type == 5: # user_data_unregistered
                    assert sei.read(16) == self.nal_sei # UUID
                    return self.read_AMF0(sei) # AMF
            
            if not buf:
                break

    def read_AMF0(self, buf):
        vals = {}
        
        assert ord(buf.read(1)) == 3
        while True:
            taglen = unpack('>H', buf.read(2))[0]
            if not taglen:
                break
            tag = buf.read(taglen).decode('ascii')
            
            valtype = ord(buf.read(1))
            if valtype == 0:
                vals[tag] = unpack('>d', buf.read(8))[0]
            elif valtype == 1:
                vals[tag] = buf.read(1) != b'\0'
            else:
                break
        
        return vals

    def read_0xff(self, buf):
        res, byte = 0, 0xff
        while byte == 0xff:
            byte = ord(buf.read(1))
            res += byte
        return res

# first=1jMJglnmwojxL bassem=1nAKEnDwRXlGL rohff=1ypJdMnmLryxW

if __name__ == '__main__':
    print(H264Reader('1BRJjlLYdYaKw').meta)
