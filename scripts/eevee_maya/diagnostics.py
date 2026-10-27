"""On-demand, name-free performance reports. No Maya or renderer dependencies."""
import math
import time


WORKER_STAGES = ('sync', 'mirror', 'depth_geometry', 'queue', 'color',
                 'depsgraph', 'draw_color', 'depth_share')


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def distribution(values):
    values = sorted(float(value) for value in values if number(value) and value >= 0)
    if not values:
        return {'count': 0, 'mean': None, 'p50': None, 'p95': None, 'max': None}

    def percentile(fraction):
        position = (len(values) - 1) * fraction
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        return values[lower] + (values[upper] - values[lower]) * (position - lower)

    return {'count': len(values), 'mean': sum(values) / len(values),
            'p50': percentile(.5), 'p95': percentile(.95), 'max': values[-1]}


def performance_report(requests, responses, presentations, now=None, window_seconds=10):
    """Count unique GPU draws, joined to this session's successful submissions.

    The draw timestamp is CPU-side, after the shared-texture draw command. It
    measures neither physical monitor scanout nor the original user's input.
    """
    now = time.perf_counter() if now is None else now
    if not number(window_seconds) or window_seconds <= 0:
        raise ValueError('La ventana de medición debe ser positiva y finita.')
    cutoff = now - window_seconds
    requests = {item['id']: item for item in requests}
    responses = {item['id']: item for item in responses if 'error' not in item}
    unique = {}
    for stamp, token, _ in presentations:
        request = requests.get(token)
        if (request is not None and number(stamp) and stamp <= now
                and number(request.get('submitted_at')) and stamp >= request['submitted_at']):
            # Repeated panel redraws are not new rendered frames. Old worker
            # sessions can reuse IDs, so timestamps must also match.
            if token not in unique or stamp < unique[token]:
                unique[token] = stamp
    unique = {token: stamp for token, stamp in unique.items() if stamp >= cutoff}
    frames = []
    for token, stamp in sorted(unique.items(), key=lambda pair: pair[1]):
        request, response = requests[token], responses.get(token, {})
        submitted = request['submitted_at']
        received = response.get('received_at')
        frames.append({
            'id': token,
            'age_seconds': now - stamp,
            'maya_frame': request.get('maya_frame') if number(request.get('maya_frame')) else None,
            'mode': request.get('mode'),
            'width': response.get('width', request.get('width')),
            'height': response.get('height', request.get('height')),
            'samples': (response.get('eevee_state') or {}).get('samples', request.get('samples')),
            'effects': {key: bool((request.get('effects') or {}).get(key)) for key in ('fog', 'bloom')},
            'dof': bool(request.get('dof')),
            'shadow_settings': {key: (request.get('shadow_settings') or {}).get(key)
                                for key in ('preset', 'resolution', 'rays', 'steps', 'pool')},
            'native': {key: (request.get('native') or {}).get(key)
                       for key in ('shadows', 'ao', 'render_dof', 'displayTextures', 'useDefaultMaterial')},
            'submit_to_draw_ms': (stamp - submitted) * 1000,
            'submit_to_receive_ms': ((received - submitted) * 1000
                                     if number(received) and received >= submitted else None),
            'worker_ms': {key: value for key, value in (response.get('timings_ms') or {}).items()
                          if key in WORKER_STAGES and number(value) and value >= 0},
        })
    times = sorted(unique.values())
    span = times[-1] - times[0] if len(times) > 1 else 0
    settings = {(frame['mode'], frame['width'], frame['height'], frame['samples'],
                 frame['dof'], tuple(frame['effects'].values()), tuple(frame['native'].values()),
                 tuple(frame['shadow_settings'].values())) for frame in frames}
    modes = {}
    resolutions = {}
    for frame in frames:
        modes[frame['mode']] = modes.get(frame['mode'], 0) + 1
        label = '%s x %s' % (frame['width'], frame['height'])
        resolutions[label] = resolutions.get(label, 0) + 1
    return {
        'schema': 1, 'window_seconds': window_seconds,
        'presented_unique_frames': len(frames),
        'contains_first_session_frame': any(frame['id'] == 1 for frame in frames),
        'observed_span_seconds': span,
        'new_gpu_frames_per_second_in_sample': (len(frames) - 1) / span if span > 0 else None,
        'new_gpu_frames_per_window_second': len(frames) / window_seconds,
        'last_new_frame_age_seconds': now - times[-1] if times else None,
        'mixed_modes_or_quality': len(settings) > 1,
        'modes': modes, 'actual_resolutions': resolutions,
        'submit_to_draw_ms': distribution(frame['submit_to_draw_ms'] for frame in frames),
        'submit_to_receive_ms': distribution(frame['submit_to_receive_ms'] for frame in frames),
        'worker_stages_ms': {key: distribution(frame['worker_ms'].get(key) for frame in frames)
                             for key in WORKER_STAGES},
        'notes': [
            'La frecuencia cuenta imágenes nuevas entre el primer y último dibujo de la muestra; no redibujos repetidos.',
            'Una pausa dentro de ese intervalo reduce la frecuencia; una ventana sin imágenes nuevas no tiene FPS medidos.',
            'La latencia comienza al enviar la escena, después de evaluarla y exportarla; no mide entrada del usuario ni scanout.',
            'Las etapas del worker se solapan: no deben sumarse como costes independientes.',
            'La muestra puede mezclar resoluciones, calidades o captura; no certifica rendimiento Full HD sostenido.',
        ],
        'frames': frames,
    }
