import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from openpilot.selfdrive.ui.onroad.augmented_road_view import AugmentedRoadView, NARROW_ROAD_CAM, WIDE_CAM


class TestView(AugmentedRoadView):
  def __del__(self):
    pass


class TestOnroadCameraToggle(unittest.TestCase):
  def _view(self):
    view = object.__new__(TestView)
    view.available_streams = [NARROW_ROAD_CAM, WIDE_CAM]
    view._stream_type = NARROW_ROAD_CAM
    view._target_stream_type = None
    view._manual_stream_type = None
    view._camera_toggle_flash_until = 0.0
    view.switch_stream = Mock()
    return view

  def test_toggle_between_wide_and_narrow(self):
    view = self._view()
    view._toggle_camera_stream()
    self.assertEqual(view._manual_stream_type, WIDE_CAM)
    view.switch_stream.assert_called_once_with(WIDE_CAM)

    view._stream_type = WIDE_CAM
    view.switch_stream.reset_mock()
    view._toggle_camera_stream()
    self.assertEqual(view._manual_stream_type, NARROW_ROAD_CAM)
    view.switch_stream.assert_called_once_with(NARROW_ROAD_CAM)

  def test_toggle_requires_wide_stream(self):
    view = self._view()
    view.available_streams = [NARROW_ROAD_CAM]
    view._toggle_camera_stream()
    self.assertIsNone(view._manual_stream_type)
    view.switch_stream.assert_not_called()

  def test_manual_view_overrides_speed_auto_switch(self):
    view = self._view()
    view._stream_type = NARROW_ROAD_CAM
    view._manual_stream_type = WIDE_CAM
    sm = {
      'carParams': SimpleNamespace(openpilotLongitudinalControl=False),
      'carState': SimpleNamespace(vEgo=30.0),
    }
    view._switch_stream_if_needed(sm)
    view.switch_stream.assert_called_once_with(WIDE_CAM)


if __name__ == '__main__':
  unittest.main()
