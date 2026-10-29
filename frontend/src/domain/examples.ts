export const SAFE_IMAGE = '{"type":"image","source":"upload","frames":[{"explicit":0.1}]}'
export const EXPLICIT_IMAGE = '{"type":"image","source":"upload","frames":[{"explicit":0.95}]}'
export const NEEDS_REVIEW = '{"type":"image","source":"upload","frames":[{"self_harm":0.66}]}'

const quietFrames = Array.from({ length: 8 }, () => '{"explicit":0.01}').join(",")
export const VIDEO_LAST_FRAME_EXPLICIT = `{"type":"video","source":"upload","frames":[${quietFrames},{"explicit":0.95}]}`
