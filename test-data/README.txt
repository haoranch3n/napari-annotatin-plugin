Napari plugin MVP test fixtures (synapse YOLO-style annotations).

Each subfolder contains:
  image.tif       — copied raw 2-channel overview .tif (full field)
  predictions.csv — columns: center_x, center_y, width, height, class_id
                    Pixel coordinates in the same reference frame as image.tif (full overview).
                    class_id: 0 = Top, 1 = Side (training convention).

case08 uses an annotation row whose file path does not contain 'KI' (alternate export path);
other cases use the standard combined-annotations table (including KI Deconv sources).

Source: combined_annotations_no_disagreements.csv + ImageAnalysisScratch.
