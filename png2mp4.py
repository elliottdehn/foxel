#!/usr/bin/env python3
"""Convert animated PNGs (as written by render.py) to H.264 MP4s.

Uses macOS AVFoundation via a small embedded Swift helper, so no ffmpeg
or third-party packages are needed. MP4s do not loop like APNGs, so the
frame sequence is repeated --loops times (default 4).

Usage: python3 png2mp4.py skeleton_walk.png [more.png ...] [--loops N]
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile
import zlib

SWIFT_HELPER = r'''
import AVFoundation
import AppKit

let args = CommandLine.arguments
let outURL = URL(fileURLWithPath: args[1])
let fps = Int32(args[2])!
let frames = Array(args[3...])

guard let first = NSImage(contentsOfFile: frames[0]),
      let cg0 = first.cgImage(forProposedRect: nil, context: nil, hints: nil)
else { fatalError("cannot read \(frames[0])") }
let width = cg0.width, height = cg0.height

try? FileManager.default.removeItem(at: outURL)
let writer = try! AVAssetWriter(outputURL: outURL, fileType: .mp4)
let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264,
    AVVideoWidthKey: width,
    AVVideoHeightKey: height,
])
let adaptor = AVAssetWriterInputPixelBufferAdaptor(
    assetWriterInput: input,
    sourcePixelBufferAttributes: [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,
        kCVPixelBufferWidthKey as String: width,
        kCVPixelBufferHeightKey as String: height,
    ])
writer.add(input)
writer.startWriting()
writer.startSession(atSourceTime: .zero)

for (i, path) in frames.enumerated() {
    while !input.isReadyForMoreMediaData {
        Thread.sleep(forTimeInterval: 0.005)
    }
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil)
    else { fatalError("cannot read \(path)") }
    var pb: CVPixelBuffer?
    CVPixelBufferCreate(kCFAllocatorDefault, width, height,
                        kCVPixelFormatType_32ARGB, nil, &pb)
    let buf = pb!
    CVPixelBufferLockBaseAddress(buf, [])
    let ctx = CGContext(
        data: CVPixelBufferGetBaseAddress(buf),
        width: width, height: height, bitsPerComponent: 8,
        bytesPerRow: CVPixelBufferGetBytesPerRow(buf),
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue)!
    ctx.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))
    CVPixelBufferUnlockBaseAddress(buf, [])
    adaptor.append(buf, withPresentationTime:
        CMTime(value: CMTimeValue(i), timescale: fps))
}
input.markAsFinished()
writer.endSession(atSourceTime:
    CMTime(value: CMTimeValue(frames.count), timescale: fps))
let sem = DispatchSemaphore(value: 0)
writer.finishWriting { sem.signal() }
sem.wait()
if writer.status != .completed {
    fatalError("write failed: \(String(describing: writer.error))")
}
'''


def read_apng(path):
    """Decode an APNG written by render.py: 8-bit RGB, filter 0, full
    frames. Returns (frames as list of bytes, width, height, fps)."""
    with open(path, 'rb') as f:
        data = f.read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('%s: not a PNG' % path)
    pos, w, h, fps, frames, ncomp = 8, None, None, None, [], 3
    while pos < len(data):
        length, tag = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b'IHDR':
            w, h, depth, ctype = struct.unpack('>IIBB', body[:10])
            if depth != 8 or ctype != 2:
                raise ValueError('%s: only 8-bit RGB supported' % path)
        elif tag == b'fcTL':
            num, den = struct.unpack('>HH', body[20:24])
            if fps is None:
                fps = max(1, round((den or 100) / max(num, 1)))
        elif tag in (b'IDAT', b'fdAT'):
            raw = zlib.decompress(body if tag == b'IDAT' else body[4:])
            stride = w * ncomp + 1
            rows = []
            for y in range(h):
                row = raw[y * stride:(y + 1) * stride]
                if row[0] != 0:
                    raise ValueError('%s: PNG filter %d not supported'
                                     % (path, row[0]))
                rows.append(row[1:])
            frames.append(b''.join(rows))
    if not frames:
        raise ValueError('%s: no image data' % path)
    return frames, w, h, fps or 12


def write_png_rgb(path, pixels, w, h):
    def chunk(tag, body):
        c = struct.pack('>I', len(body)) + tag + body
        return c + struct.pack('>I', zlib.crc32(tag + body))
    stride = w * 3
    raw = b''.join(b'\x00' + pixels[y * stride:(y + 1) * stride]
                   for y in range(h))
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b'IDAT', zlib.compress(raw, 6)))
        f.write(chunk(b'IEND', b''))


def convert(path, loops, output=None):
    frames, w, h, fps = read_apng(path)
    out = output or os.path.splitext(path)[0] + '.mp4'
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for i, fr in enumerate(frames):
            p = os.path.join(tmp, 'f%04d.png' % i)
            write_png_rgb(p, fr, w, h)
            files.append(p)
        helper = os.path.join(tmp, 'frames2mp4.swift')
        with open(helper, 'w') as f:
            f.write(SWIFT_HELPER)
        seq = files * loops
        r = subprocess.run(['swift', helper, os.path.abspath(out),
                            str(fps)] + seq,
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit('swift helper failed:\n%s' % (r.stderr or r.stdout))
    print('wrote %s (%d frames x %d loops @ %d fps, %dx%d)'
          % (out, len(frames), loops, fps, w, h))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('inputs', nargs='+', help='animated PNG files')
    ap.add_argument('--loops', type=int, default=4,
                    help='repeat the loop N times in the video (default 4)')
    ap.add_argument('-o', '--output',
                    help='output file (single input only)')
    args = ap.parse_args()
    if args.output and len(args.inputs) > 1:
        sys.exit('-o only works with a single input')
    for path in args.inputs:
        convert(path, args.loops, args.output)


if __name__ == '__main__':
    main()
