export interface EncodedDims {
  src_width: number;
  src_height: number;
  display_width: number;
  display_height: number;
  scale: number;
}

export function getStageDimensions(encoded: EncodedDims): {
  width: number;
  height: number;
} {
  return {
    width: encoded.display_width,
    height: encoded.display_height,
  };
}
