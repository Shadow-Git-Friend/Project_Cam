# arena_fixed

Изолированный подпроект для проверки и фикса системы координат арены (в первую очередь `Y`), без изменений в основном пайплайне `garage_lab_combined`.

## Цель

- Не трогать текущие рабочие файлы.
- Иметь отдельные копии `Dimensions.txt` и `extrinsics`.
- Быстро проверять, что по `Y`:
  - `camEast` и теги `20,16,19,17,18,21,22` находятся около `Y≈0`.
  - `camWest` и теги `11,12,13,14,15,10,0` находятся около `Y≈Ymax`.

## Что внутри

- `cal/extrinsics/Dimensions_fixed.txt` — фиксированная версия (East-side `Y=0`, как в исходной логике).
- `cal/extrinsics/Dimensions_mirrored_y.txt` — альтернативная зеркальная версия (`y' = Ymax - y`) только для отладки.
- `cal/extrinsics/extrinsics_fixed.json` — копия исходных extrinsics.
- `reports/y_axis_report.md` и `reports/y_axis_report.json` — валидация размещения по `Y`.
- `scripts/build_arena_fixed.py` — сборка и пересчет арены в этой папке.

## Пересобрать arena_fixed

```bash
cd /home/hanush/Desktop/Project_Cam
./venv/bin/python arena_fixed/scripts/build_arena_fixed.py
```

## Запуск live viewer

```bash
cd /home/hanush/Desktop/Project_Cam
./venv/bin/python garage_lab_combined/scripts/live_4cam_arena_view.py \
  --config garage_lab_combined/config/cameras.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json \
  --dimensions arena_fixed/cal/extrinsics/Dimensions_fixed.txt \
  --no-world-y-mirror \
  --draw-global-axes \
  --global-axis-len-mm 900
```

### Два режима для сравнения оси Y

- `run_live_visual_invert_only.sh`:
  - только визуальная инверсия оси в 3D (`--invert-y-axis-display`);
  - мир/UDP не зеркалятся (`--no-world-y-mirror`).
- `run_live_mirrored_debug.sh`:
  - реальный mirror world (`--world-y-mirror`) для 3D и UDP;
  - подписи оси без доп. инверсии (`--no-invert-y-axis-display`).

Примеры запуска:

```bash
cd /home/hanush/Desktop/Project_Cam
./arena_fixed/run_live_visual_invert_only.sh --udp-target-host 127.0.0.1 --udp-target-port 5005
./arena_fixed/run_live_mirrored_debug.sh --udp-target-host 127.0.0.1 --udp-target-port 5005
```

## Важно

- `Dimensions_mirrored_y.txt` не используется в прод-ране по умолчанию.
- Для runtime/UDP используйте `Dimensions_fixed.txt`, чтобы не ломать существующую геометрию.
- `run_live_visual_invert_only.sh`: инверсия оси `Y` только в отображении (3D labels), без влияния на triangulation/UDP.
- `run_live_mirrored_debug.sh`: mirrored world (`y' = Ymax - y`) для 3D/UDP и общий origin для `X=0, Y=0, Z=0` в одном углу mirrored-frame.
- `run_live_mirrored_inverted_y_labels.sh`: тот же mirrored world, но с инвертированными подписями оси `Y` (`Ymax..0`) для визуального сравнения.
