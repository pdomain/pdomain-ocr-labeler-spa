// Coordinate system transformations between source image pixels and display pixels.
// scale = encoded.display_width / encoded.src_width

export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

// Multiply x/y/width/height by scale to convert from source to display pixels
export function srcToDisplay(bbox: BBox, scale: number): BBox {
  return {
    x: bbox.x * scale,
    y: bbox.y * scale,
    width: bbox.width * scale,
    height: bbox.height * scale,
  };
}

// Divide by scale and round to convert from display to source pixels
export function displayToSrc(bbox: BBox, scale: number): BBox {
  return {
    x: Math.round(bbox.x / scale),
    y: Math.round(bbox.y / scale),
    width: Math.round(bbox.width / scale),
    height: Math.round(bbox.height / scale),
  };
}
