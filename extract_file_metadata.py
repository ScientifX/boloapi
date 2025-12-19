"""
File Metadata Extraction Script
================================
Scans the bolo_cache directory and extracts metadata from all cached files.
Outputs:
  - metadata_results.json: Full metadata for each file
  - metadata_summary.csv: Summary table for analysis

Supports: JPG, PNG, PDF, BIN (auto-detected), GIF, WEBP, TIFF

Requirements:
    pip install Pillow exifread PyMuPDF python-magic-bin --break-system-packages

Usage:
    python extract_file_metadata.py [--cache-dir PATH] [--output-dir PATH] [--limit N]
"""

import os
import sys
import json
import csv
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict

# Try importing optional libraries
try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("WARNING: Pillow not installed. Install with: pip install Pillow")

try:
    import exifread
    HAS_EXIFREAD = True
except ImportError:
    HAS_EXIFREAD = False
    print("WARNING: exifread not installed. Install with: pip install exifread")

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("WARNING: PyMuPDF not installed. Install with: pip install PyMuPDF")

# Magic bytes for file type detection
MAGIC_BYTES = {
    b'\xff\xd8\xff': 'jpg',
    b'\x89PNG\r\n\x1a\n': 'png',
    b'GIF87a': 'gif',
    b'GIF89a': 'gif',
    b'%PDF': 'pdf',
    b'RIFF': 'webp',  # RIFF....WEBP
    b'II*\x00': 'tiff',  # Little-endian TIFF
    b'MM\x00*': 'tiff',  # Big-endian TIFF
}


def detect_file_type(file_path: Path) -> str:
    """Detect actual file type from magic bytes."""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(12)
        
        for magic, file_type in MAGIC_BYTES.items():
            if header.startswith(magic):
                # Special case for WEBP (RIFF....WEBP)
                if magic == b'RIFF' and b'WEBP' in header:
                    return 'webp'
                elif magic == b'RIFF':
                    continue  # Not WEBP, could be other RIFF format
                return file_type
        
        # Check for WEBP specifically
        if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
            return 'webp'
        
        return 'unknown'
    except Exception:
        return 'unknown'


def compute_file_hash(file_path: Path, algorithm: str = 'sha256') -> str:
    """Compute hash of file contents."""
    h = hashlib.new(algorithm)
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def get_basic_file_info(file_path: Path) -> Dict[str, Any]:
    """Get basic file information available for all files."""
    stat = file_path.stat()
    detected_type = detect_file_type(file_path)
    
    return {
        'filename': file_path.name,
        'extension': file_path.suffix.lower(),
        'detected_type': detected_type,
        'file_size_bytes': stat.st_size,
        'file_size_kb': round(stat.st_size / 1024, 2),
        'file_size_mb': round(stat.st_size / (1024 * 1024), 4),
        'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
        'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
        'sha256_hash': compute_file_hash(file_path, 'sha256'),
        'md5_hash': compute_file_hash(file_path, 'md5'),
    }


def convert_gps_to_decimal(gps_coords, gps_ref) -> Optional[float]:
    """Convert GPS coordinates from DMS to decimal degrees."""
    try:
        if hasattr(gps_coords, 'values'):
            # exifread format
            d = float(gps_coords.values[0].num) / float(gps_coords.values[0].den)
            m = float(gps_coords.values[1].num) / float(gps_coords.values[1].den)
            s = float(gps_coords.values[2].num) / float(gps_coords.values[2].den)
        else:
            # PIL format (tuple of ratios)
            d, m, s = gps_coords
            if hasattr(d, 'numerator'):
                d = d.numerator / d.denominator
                m = m.numerator / m.denominator
                s = s.numerator / s.denominator
        
        decimal = d + (m / 60.0) + (s / 3600.0)
        
        if gps_ref in ['S', 'W']:
            decimal = -decimal
        
        return round(decimal, 8)
    except Exception:
        return None


def extract_exif_with_exifread(file_path: Path) -> Dict[str, Any]:
    """Extract EXIF using exifread library (more thorough)."""
    exif_data = {}
    gps_data = {}
    
    try:
        with open(file_path, 'rb') as f:
            tags = exifread.process_file(f, details=True)
        
        if not tags:
            return {'exif_present': False}
        
        # Extract relevant tags
        tag_mapping = {
            'Image Make': 'camera_make',
            'Image Model': 'camera_model',
            'EXIF DateTimeOriginal': 'datetime_original',
            'EXIF DateTimeDigitized': 'datetime_digitized',
            'Image DateTime': 'datetime_modified',
            'EXIF ExposureTime': 'exposure_time',
            'EXIF FNumber': 'f_number',
            'EXIF ISOSpeedRatings': 'iso',
            'EXIF FocalLength': 'focal_length',
            'EXIF Flash': 'flash',
            'EXIF ExifImageWidth': 'exif_width',
            'EXIF ExifImageLength': 'exif_height',
            'Image XResolution': 'x_resolution',
            'Image YResolution': 'y_resolution',
            'Image ResolutionUnit': 'resolution_unit',
            'EXIF ColorSpace': 'color_space',
            'Image Software': 'software',
            'Image Artist': 'artist',
            'Image Copyright': 'copyright',
            'EXIF LensModel': 'lens_model',
            'EXIF LensSerialNumber': 'lens_serial',
            'EXIF BodySerialNumber': 'body_serial',
        }
        
        for tag_name, field_name in tag_mapping.items():
            if tag_name in tags:
                value = str(tags[tag_name])
                if value and value != '0':
                    exif_data[field_name] = value
        
        # Extract GPS data
        gps_tags = {k: v for k, v in tags.items() if k.startswith('GPS')}
        
        if 'GPS GPSLatitude' in tags and 'GPS GPSLatitudeRef' in tags:
            lat = convert_gps_to_decimal(
                tags['GPS GPSLatitude'],
                str(tags['GPS GPSLatitudeRef'])
            )
            if lat is not None:
                gps_data['latitude'] = lat
        
        if 'GPS GPSLongitude' in tags and 'GPS GPSLongitudeRef' in tags:
            lon = convert_gps_to_decimal(
                tags['GPS GPSLongitude'],
                str(tags['GPS GPSLongitudeRef'])
            )
            if lon is not None:
                gps_data['longitude'] = lon
        
        if 'GPS GPSAltitude' in tags:
            try:
                alt = tags['GPS GPSAltitude'].values[0]
                gps_data['altitude'] = float(alt.num) / float(alt.den)
            except Exception:
                pass
        
        if 'GPS GPSDateStamp' in tags:
            gps_data['gps_date'] = str(tags['GPS GPSDateStamp'])
        
        result = {
            'exif_present': bool(exif_data or gps_data),
            'exif_tag_count': len(tags),
        }
        
        if exif_data:
            result['exif'] = exif_data
        
        if gps_data:
            result['gps'] = gps_data
            result['has_gps'] = True
        else:
            result['has_gps'] = False
        
        return result
        
    except Exception as e:
        return {'exif_present': False, 'exif_error': str(e)}


def extract_image_metadata_pil(file_path: Path) -> Dict[str, Any]:
    """Extract image metadata using PIL."""
    try:
        with Image.open(file_path) as img:
            metadata = {
                'width': img.width,
                'height': img.height,
                'format': img.format,
                'mode': img.mode,
                'is_animated': getattr(img, 'is_animated', False),
                'n_frames': getattr(img, 'n_frames', 1),
            }
            
            # Get DPI if available
            if hasattr(img, 'info') and 'dpi' in img.info:
                dpi = img.info['dpi']
                metadata['dpi_x'] = dpi[0]
                metadata['dpi_y'] = dpi[1]
            
            # Color analysis
            try:
                # Get dominant colors (simplified)
                small = img.copy()
                small.thumbnail((100, 100))
                if small.mode != 'RGB':
                    small = small.convert('RGB')
                
                colors = small.getcolors(maxcolors=10000)
                if colors:
                    # Sort by frequency
                    colors.sort(key=lambda x: x[0], reverse=True)
                    top_colors = colors[:5]
                    metadata['dominant_colors'] = [
                        {'rgb': c[1], 'count': c[0]} for c in top_colors
                    ]
            except Exception:
                pass
            
            return metadata
            
    except Exception as e:
        return {'image_error': str(e)}


def extract_pdf_metadata(file_path: Path) -> Dict[str, Any]:
    """Extract PDF metadata using PyMuPDF."""
    if not HAS_PYMUPDF:
        return {'pdf_error': 'PyMuPDF not installed'}
    
    try:
        doc = fitz.open(file_path)
        
        metadata = {
            'page_count': doc.page_count,
            'pdf_version': doc.metadata.get('format', ''),
            'is_encrypted': doc.is_encrypted,
            'is_pdf': doc.is_pdf,
        }
        
        # Standard PDF metadata fields
        pdf_fields = ['title', 'author', 'subject', 'keywords', 'creator', 
                      'producer', 'creationDate', 'modDate']
        
        for field in pdf_fields:
            value = doc.metadata.get(field)
            if value:
                metadata[f'pdf_{field.lower()}'] = value
        
        # Get page dimensions from first page
        if doc.page_count > 0:
            page = doc[0]
            rect = page.rect
            metadata['page_width_pt'] = rect.width
            metadata['page_height_pt'] = rect.height
            metadata['page_width_in'] = round(rect.width / 72, 2)
            metadata['page_height_in'] = round(rect.height / 72, 2)
        
        # Check if text is extractable
        try:
            if doc.page_count > 0:
                text = doc[0].get_text()
                metadata['has_extractable_text'] = len(text.strip()) > 0
                metadata['first_page_char_count'] = len(text)
        except Exception:
            metadata['has_extractable_text'] = False
        
        # Count images in document
        try:
            image_count = 0
            for page_num in range(min(doc.page_count, 10)):  # Check first 10 pages
                image_count += len(doc[page_num].get_images())
            metadata['image_count_sample'] = image_count
        except Exception:
            pass
        
        doc.close()
        return metadata
        
    except Exception as e:
        return {'pdf_error': str(e)}


def extract_png_metadata(file_path: Path) -> Dict[str, Any]:
    """Extract PNG-specific metadata (text chunks)."""
    metadata = {}
    
    try:
        with Image.open(file_path) as img:
            # PNG text chunks stored in img.info
            if hasattr(img, 'info'):
                text_chunks = {}
                for key, value in img.info.items():
                    if isinstance(value, str) and key not in ['dpi', 'gamma']:
                        text_chunks[key] = value
                
                if text_chunks:
                    metadata['png_text_chunks'] = text_chunks
            
            # PNG-specific attributes
            if hasattr(img, 'text'):
                metadata['png_text'] = dict(img.text)
    
    except Exception as e:
        metadata['png_error'] = str(e)
    
    return metadata


def process_file(file_path: Path) -> Dict[str, Any]:
    """Process a single file and extract all available metadata."""
    result = get_basic_file_info(file_path)
    
    # Determine actual file type
    file_type = result['detected_type']
    if file_type == 'unknown':
        file_type = result['extension'].lstrip('.')
    
    result['processed_as'] = file_type
    
    # Process based on file type
    if file_type in ['jpg', 'jpeg']:
        # JPEG: Full EXIF support
        if HAS_PIL:
            pil_meta = extract_image_metadata_pil(file_path)
            result.update(pil_meta)
        
        if HAS_EXIFREAD:
            exif_meta = extract_exif_with_exifread(file_path)
            result.update(exif_meta)
    
    elif file_type == 'png':
        # PNG: Limited metadata
        if HAS_PIL:
            pil_meta = extract_image_metadata_pil(file_path)
            result.update(pil_meta)
            png_meta = extract_png_metadata(file_path)
            result.update(png_meta)
        
        result['exif_present'] = False
        result['has_gps'] = False
    
    elif file_type in ['gif', 'webp', 'tiff']:
        # Other image formats
        if HAS_PIL:
            pil_meta = extract_image_metadata_pil(file_path)
            result.update(pil_meta)
        
        if file_type == 'tiff' and HAS_EXIFREAD:
            exif_meta = extract_exif_with_exifread(file_path)
            result.update(exif_meta)
    
    elif file_type == 'pdf':
        # PDF metadata
        pdf_meta = extract_pdf_metadata(file_path)
        result.update(pdf_meta)
        result['exif_present'] = False
        result['has_gps'] = False
    
    else:
        # Unknown or binary file
        result['exif_present'] = False
        result['has_gps'] = False
    
    return result


def generate_summary_row(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a flattened summary row for CSV."""
    return {
        'filename': metadata.get('filename', ''),
        'extension': metadata.get('extension', ''),
        'detected_type': metadata.get('detected_type', ''),
        'file_size_kb': metadata.get('file_size_kb', 0),
        'width': metadata.get('width', ''),
        'height': metadata.get('height', ''),
        'has_exif': metadata.get('exif_present', False),
        'has_gps': metadata.get('has_gps', False),
        'latitude': metadata.get('gps', {}).get('latitude', ''),
        'longitude': metadata.get('gps', {}).get('longitude', ''),
        'camera_make': metadata.get('exif', {}).get('camera_make', ''),
        'camera_model': metadata.get('exif', {}).get('camera_model', ''),
        'datetime_original': metadata.get('exif', {}).get('datetime_original', ''),
        'page_count': metadata.get('page_count', ''),
        'sha256_hash': metadata.get('sha256_hash', '')[:16] + '...',
    }


def main():
    parser = argparse.ArgumentParser(description='Extract metadata from cached BOLO files')
    parser.add_argument('--cache-dir', type=str, default='data/bolo_cache',
                        help='Path to cache directory (default: data/bolo_cache)')
    parser.add_argument('--output-dir', type=str, default='.',
                        help='Output directory for results (default: current directory)')
    parser.add_argument('--limit', type=int, default=0,
                        help='Limit number of files to process (0 = all)')
    parser.add_argument('--extensions', type=str, default='',
                        help='Comma-separated list of extensions to process (empty = all)')
    args = parser.parse_args()
    
    cache_dir = Path(args.cache_dir)
    output_dir = Path(args.output_dir)
    
    if not cache_dir.exists():
        print(f"ERROR: Cache directory not found: {cache_dir}")
        sys.exit(1)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Get list of files
    files = list(cache_dir.iterdir())
    files = [f for f in files if f.is_file()]
    
    # Filter by extension if specified
    if args.extensions:
        ext_filter = [f'.{e.strip().lower()}' for e in args.extensions.split(',')]
        files = [f for f in files if f.suffix.lower() in ext_filter]
    
    # Apply limit
    if args.limit > 0:
        files = files[:args.limit]
    
    print(f"Processing {len(files)} files from {cache_dir}")
    print(f"Libraries available: PIL={HAS_PIL}, exifread={HAS_EXIFREAD}, PyMuPDF={HAS_PYMUPDF}")
    print("-" * 60)
    
    # Process files
    results = []
    stats = defaultdict(int)
    
    for i, file_path in enumerate(files, 1):
        if i % 100 == 0 or i == len(files):
            print(f"Progress: {i}/{len(files)} files processed...")
        
        try:
            metadata = process_file(file_path)
            results.append(metadata)
            
            # Update stats
            stats['total'] += 1
            stats[f"type_{metadata.get('detected_type', 'unknown')}"] += 1
            
            if metadata.get('exif_present'):
                stats['has_exif'] += 1
            if metadata.get('has_gps'):
                stats['has_gps'] += 1
                
        except Exception as e:
            print(f"ERROR processing {file_path.name}: {e}")
            stats['errors'] += 1
    
    # Write JSON output
    json_path = output_dir / 'metadata_results.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'extraction_date': datetime.now().isoformat(),
            'source_directory': str(cache_dir),
            'files_processed': len(results),
            'statistics': dict(stats),
            'files': results
        }, f, indent=2, default=str)
    
    print(f"\nJSON output: {json_path}")
    
    # Write CSV summary
    csv_path = output_dir / 'metadata_summary.csv'
    if results:
        fieldnames = [
            'filename', 'extension', 'detected_type', 'file_size_kb',
            'width', 'height', 'has_exif', 'has_gps', 'latitude', 'longitude',
            'camera_make', 'camera_model', 'datetime_original', 'page_count',
            'sha256_hash'
        ]
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for metadata in results:
                writer.writerow(generate_summary_row(metadata))
    
    print(f"CSV output: {csv_path}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"Total files processed: {stats['total']}")
    print(f"Errors: {stats.get('errors', 0)}")
    print("\nBy detected type:")
    for key, value in sorted(stats.items()):
        if key.startswith('type_'):
            print(f"  {key.replace('type_', ''):12} {value:,}")
    print(f"\nFiles with EXIF data: {stats.get('has_exif', 0)}")
    print(f"Files with GPS data:  {stats.get('has_gps', 0)}")
    print("=" * 60)


if __name__ == '__main__':
    main()
