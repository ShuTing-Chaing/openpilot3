import unittest

from openpilot.selfdrive.ui.onroad.augmented_road_view import (
  NARROW_ROAD_CAM,
  ROAD_CAMERA_VIEW_AUTO,
  ROAD_CAMERA_VIEW_STANDARD,
  ROAD_CAMERA_VIEW_WIDE,
  WIDE_CAM,
  camera_stream_target,
)


class TestRoadCameraViewMode(unittest.TestCase):
  def test_auto_switches_by_speed(self):
    available = [NARROW_ROAD_CAM, WIDE_CAM]
    self.assertEqual(camera_stream_target(ROAD_CAMERA_VIEW_AUTO, NARROW_ROAD_CAM, 2.0, True, available), WIDE_CAM)
    self.assertEqual(camera_stream_target(ROAD_CAMERA_VIEW_AUTO, WIDE_CAM, 12.0, True, available), NARROW_ROAD_CAM)
    self.assertEqual(camera_stream_target(ROAD_CAMERA_VIEW_AUTO, WIDE_CAM, 7.5, True, available), WIDE_CAM)
    self.assertEqual(camera_stream_target(ROAD_CAMERA_VIEW_AUTO, NARROW_ROAD_CAM, 7.5, True, available), NARROW_ROAD_CAM)

  def test_wide_mode_overrides_speed(self):
    self.assertEqual(
      camera_stream_target(ROAD_CAMERA_VIEW_WIDE, NARROW_ROAD_CAM, 30.0, False, [NARROW_ROAD_CAM, WIDE_CAM]),
      WIDE_CAM,
    )

  def test_standard_mode_overrides_speed(self):
    self.assertEqual(
      camera_stream_target(ROAD_CAMERA_VIEW_STANDARD, WIDE_CAM, 0.0, True, [NARROW_ROAD_CAM, WIDE_CAM]),
      NARROW_ROAD_CAM,
    )

  def test_missing_wide_stream_falls_back_to_standard(self):
    self.assertEqual(
      camera_stream_target(ROAD_CAMERA_VIEW_WIDE, NARROW_ROAD_CAM, 0.0, True, [NARROW_ROAD_CAM]),
      NARROW_ROAD_CAM,
    )


if __name__ == '__main__':
  unittest.main()
