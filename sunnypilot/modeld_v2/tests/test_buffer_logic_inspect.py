from openpilot.sunnypilot.modeld_v2.combined_runtime import (
  _detect_desire_key, derive_frame_skip, make_split_input_queues, make_supercombo_input_queues,
)


VISION_SHAPES = {
  'img': (1, 12, 128, 256),
  'big_img': (1, 12, 128, 256),
}


def test_derive_frame_skip():
  assert derive_frame_skip({}, {'features_buffer': (1, 99, 512)}) == 1
  assert derive_frame_skip({}, {'features_buffer': (1, 24, 512)}) == 4
  assert derive_frame_skip({}, {}) == 1


def test_detect_desire_key_variants():
  assert _detect_desire_key({'desire': (1, 100, 8)}) == 'desire'
  assert _detect_desire_key({'desire_pulse': (1, 25, 8)}) == 'desire_pulse'
  assert _detect_desire_key({'features_buffer': (1, 24, 512)}) is None


def test_supercombo_queue_shapes():
  shapes = {
    **VISION_SHAPES,
    'features_buffer': (1, 24, 512),
    'desire_pulse': (1, 25, 8),
    'traffic_convention': (1, 2),
    'action_t': (1, 2),
  }
  queues, numpy_inputs = make_supercombo_input_queues(shapes, frame_skip=4, device='NPY')

  assert tuple(queues['img_q'].shape) == (5, 6, 128, 256)
  assert tuple(queues['big_img_q'].shape) == (5, 6, 128, 256)
  assert tuple(queues['desire_q'].shape) == (100, 1, 8)
  assert tuple(queues['feat_q'].shape) == (96, 1, 512)
  assert tuple(queues['packed_npy_inputs'].shape) == (524,)
  assert numpy_inputs['desire'].shape == (8,)
  assert numpy_inputs['prev_feat'].shape == (1, 512)
  assert numpy_inputs['traffic_convention'].shape == (1, 2)
  assert numpy_inputs['action_t'].shape == (1, 2)


def test_split_queue_shapes():
  policy_shapes = {
    'features_buffer': (1, 25, 512),
    'desire': (1, 25, 8),
    'traffic_convention': (1, 2),
  }
  queues, numpy_inputs = make_split_input_queues(VISION_SHAPES, policy_shapes, frame_skip=4, device='NPY')

  assert tuple(queues['feat_q'].shape) == (97, 1, 512)
  assert tuple(queues['desire_q'].shape) == (100, 1, 8)
  assert tuple(queues['packed_npy_inputs'].shape) == (10,)
  assert 'prev_feat' not in numpy_inputs
