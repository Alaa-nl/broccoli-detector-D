// Single source of truth for the model facts shown in the UI, so the Home
// and Settings pages can't drift apart. Update these here when the model
// is retrained.
export const MODEL_INFO = {
  architecture: 'YOLOv8n (Ultralytics)',
  parameters: '3.0M',
  trainingMap: '0.976',
  meanIoU: '0.916',
  weights: 'best.pt (about 6 MB)',
  testSetSize: 27,
};
