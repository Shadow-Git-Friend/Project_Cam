# Project_Cam — Execution Plan

**Создан:** 2026-04-14
**Контекст:** MSc thesis (защита ~4–5 недель) + подготовка питча для Академии Кайрата / спорт-теч фондов.
**Базируется на:** `suggestions.md` (обзор + вердикты), CLAUDE.md (текущий статус), thesis_engineering_chapter.md, thesis_defense_qa.md.

---

## Historical planning context (superseded 2026-04-14)

До этого документа был `recommended_implementation_order.md` (2026-03-26) — план FPS-оптимизации для `live_4cam_arena_view.py`. Большая часть его реализована и задокументирована в CLAUDE.md:

- **Step 1 (StageTimer profiling)** → реализовано как `--perf-log-every` / `--perf-jsonl`
- **Step 2 (ThreadedCapture)** → реализовано в `Parallel_working/scripts/live_4cam_arena_view_parallel.py`
- **Step 3 (cv2 3D renderer вместо matplotlib)** → реализовано, ~2 ms на кадр vs 80–200 ms
- **Step 4 (shell presets)** → реализовано: quality / balanced / smooth / smooth_v2 / predictive / yolopose
- **Step 5 (validation)** → зафиксировано в `.claude/rules/geometry.md` (guardrails) и GT-eval трейлах
- **Step 6 (batch undistort)** → отложено, см. `suggestions.md` — нет практического выигрыша
- **Step 7 (downscaled inference)** → отброшено: 960×540 maxfps вызвал скелет-drift (см. CLAUDE.md)
- **Step 8 (parallel CUDA streams)** → реализовано через multiprocessing в `Parallel_working/`
- **Step 9 (direct RTMPose ONNX)** → обошли через YOLO11m-Pose single-model (6.2× быстрее, ablation 2026-04-06)

Safe-tuning matrix (ema-alpha, pose-every, ball-every, viz-every и т.д.) перенесён в `.claude/rules/perf.md` и остаётся живым.

**Этот план (Phase 0–5 ниже) — текущий источник правды.** Старый FPS-документ удалён 2026-04-17 как полностью поглощённый.

---

## Принципы

1. **Не трогать работающее до защиты.** S0–S4 пройдены 2026-04-09. Любой крупный рефакторинг сейчас = риск сломать демо.
2. **Код — инструмент, не продукт.** Инвестор не читает код. Панель не спрашивает архитектуру.
3. **Каждая фаза заканчивается артефактом**, который можно показать (видео / демо / PDF / работающий prototype).
4. **Отбрасывать enterprise-советы**, пока не будет второго разработчика или второго спорта.

---

## Phase 0 — Стабилизация (осталось из прошлых итераций)

**Срок:** 2–3 дня
**Статус:** in-progress

- [x] TRT engines с dynamic batch=4 (ball + pose) — 2026-04-13
- [x] Robust ball triangulation + Kalman в live viewer — 2026-04-13
- [x] SIGTERM handler для recording (MP4 finalize) — 2026-04-13
- [x] **Запись 3 сценариев (slow / fast / bounce)** — 2026-04-15 (`mosaic2d_20260415_132*.mp4`)
- [x] **Offline ball-detection sweep** — `Parallel_working/scripts/ball_detection_analyzer.py` (2026-04-20). Показал: conf=0.40 отбрасывает 40–60% recoverable detections на bounce/fast; imgsz=672→960 поднимает camNorth bounce 58%→98%.
- [x] **Single-cam fallback в live viewer** — `project_ray_to_z_plane` + `--ball-single-cam-fallback` (2026-04-20). Geometry-safe, flag-guarded, off by default. Фиксирует структурную проблему "ball disappears when <2 cams see it".
- [ ] **Live-lab тест новых флагов** — `--ball-imgsz 960 --ball-single-cam-fallback`, bounce + fast в арене. Если стабильно → flip defaults отдельным коммитом.
- [ ] **Запись `bounce_01` per-cam sequence** через `record_test_sequence.py` — seed для Phase 1 regression fixture (R1 keystone).
- [ ] **Ball speed calibration (RPM→m/s curve)**
  - Выстрелы на 500/600/700/800/900 RPM
  - Измерить скорость через 2 кадра + известное расстояние
  - Записать в `garage_lab_combined/cal/ball_rpm_to_speed.json`
  - Обновить `_blm_solve` чтобы брать v_ms из таблицы, а не хардкода 10 м/с

**Exit criteria:** запись 30-секундного тестового прогона, где мяч видно плавно, без teleports, скелет нарисован.

---

## Phase 0b — Projector goal game fix + camera upgrade (2026-05-29)

**Контекст:** диагностировали, почему projector goal game почти не засчитывает. Это **софт-баг + метод**, НЕ сломанная калибровка. Доказано численно на реальных `Remounted_West_East/` файлах. Подробности — `.claude/rules/{geometry,workflow}.md` и Session Log в CLAUDE.md.

### Софт-фиксы (бесплатно, geometry-protected функции не трогаем)
- [ ] **Phase 0 — доказать калибровку:** static-ball validator, триангуляция мяча видимого ≥2 камерами с правильной парой (normalized obs + `[R|t]`), gate **< 25 px**. Калибровка здорова (intrinsics @1920×1080 RMS 1.0–1.3 px, extrinsics RMSE 2.8–3.4 px).
- [ ] **Phase 1 — one-liner:** `goal_target_game_multicam.py` `proj_mats[cam] = K @ e["P"]` → `e["P"]` (как в canonical viewer). Gate: `tri_reproj_err_px` ~1400 → <25 px.
- [ ] **Phase 2 — переписать scoring** с per-cam wall consensus на **3D триангуляция → KF → пересечение X=6230 → зона**; consensus оставить fallback; **camSouth исключить из wall-voting** (camSouth НЕ двигаем, он ценен для 3D). 
- [ ] **Phase 3 — переснять `homography.json`** при проекторе залоченном на **1920×1080** (сейчас proj_h=1200 = высота монитора → grid смещён только визуально).
- [ ] **Phase 4 — приёмка:** reproj <25 px, `no-consensus` падает, реальные удары засчитываются.

### Камеры — placement decision
- **Оставляем текущую 4-камерную геометрию. camSouth НЕ двигаем** (отклонили рекомендацию deep-research «перенести на NW» — убивает south-end покрытие, основана на ложной посылке «калибровка сломана»). Реальный FOV из K = HFOV 81–86°.

### Камеры — закупка (для профессора, GigE global-shutter)
- [ ] Купить **4** (1:1 замена; не смешивать типы затвора). Primary **4× HikRobot MV-CS016-10GC** (1.6 MP GS, GigE-PoE, HW trigger — GigE вариант это IMX296 ~65 fps, НЕ IMX273) или **4× FLIR BFS-PGE-16S2C-CS** (IMX273 78 fps, ~$371). Линзы ~3.5–4 мм (НЕ 6 мм).
- [ ] Подключение: **Intel I350-T4** quad GigE NIC (по линии на камеру) + 12 В и ESP32 opto-trigger через Hirose I/O (PoE не нужен). User хочет **raw запись @ 60 fps** → добавить **2 TB NVMe** (M.2). Итого ≈ $1,500–1,900.
- **PC (HP Z4 G4: i9-7900X, 32 GB, RTX 2080 Ti + Quadro P400) тянет всё** — единственные добавки: NIC + NVMe. «Докупить 4 веб-камеры (→8)» отклонено: не чинит sync/rolling-shutter, ломает USB-2 бюджет, режет inference fps вдвое.
- Закупка ортогональна софт-фиксу: камеры чинят быстрый мяч (hardware ceiling), софт-фикс чинит scoring.

**Exit criteria:** goal game засчитывает удары (bounce/slow) после софт-фиксов; BoM отправлен профессору, процедура закупки запущена.

---

## Phase 1 — Pre-defense housekeeping

**Срок:** 1 неделя (примерно последняя неделя до защиты)
**Цель:** подтянуть слабые места, которые панель может заметить, **без архитектурных переделок**.

### 1.1 Минимальный refactoring (совпадает с рекомендацией обеих LLM)

- [ ] **`garage_lab_combined/scripts/common.py`** (~1 час)
  - Перенести из дублей: `solve_angles_ballistic`, `world_to_launcher_xy_delta`, `apply_correction`, `load_correction_model`
  - Импортировать из `blm_follow.py`, `live_aim_test.py`, `launcher_runtime_from_udp.py`
  - В thesis описать как «refactoring round for maintainability»

- [ ] **`ArenaConfig` (pydantic)** (~1 час)
  - `arena_fixed/cal/arena.yaml` — один источник правды по размерам, позиции BLM, bias-модели
  - Загружать в обоих runtime-скриптах
  - В thesis упомянуть как «configuration as code»

### 1.2 Defense прогоны

- [ ] Прогнать Q&A pack вслух по таймеру
- [ ] Проверить слайды: ECE-панель спрашивает про hardware → слайды 1–8 hardware, 9–12 vision, 13–15 safety, 16–18 results
- [ ] Записать 1-минутное back-up demo видео (на случай если железо сломается)

**Exit criteria:** защита пройдена.

---

## Phase 2 — Post-defense unlock (1 неделя)

**Срок:** первая неделя после защиты
**Цель:** зафиксировать результат, собрать материал для питча.

### 2.1 Документация

- [ ] Отдельная папка `startup_pitch/` — не трогать thesis-файлы
- [ ] **One-pager PDF** (1 страница):
  - Problem: тренировка вратарей/атакующих = дорогой тренер + повторяемость
  - Solution: автоматическая пушка с pose-guided targeting
  - Metrics: precision 4.4 мм (после correction), 15 FPS, latency <50 мс
  - Safety: 10-layer architecture (со ссылкой на ISO 12100)
  - Ask: $X для пилота в одном клубе (6 месяцев)

### 2.2 Demo video (главный артефакт)

- [ ] Запись 4K на нормальную камеру (не webcam)
- [ ] 3 сценария:
  - **Goalkeeper reaction test:** пушка стреляет в дальний от вратаря угол, измеряется время реакции.
  - **Targeted shot:** игрок поднимает руку → пушка попадает в поднятую руку (демонстрация joint-level targeting).
  - **Reload → aim → shoot cycle:** полный замкнутый цикл с reload'ом.
- [ ] 3 версии длиной 15 сек / 60 сек / 3 мин — для разных каналов (Telegram / Instagram / pitch deck).

**Exit criteria:** 3 видео + PDF one-pager готовы.

---

## Phase 3 — Продуктовый MVP для питча (2–3 недели)

**Срок:** недели 2–4 после защиты
**Цель:** превратить CLI-демо в продукт, который тренер может запустить сам.

### 3.1 UI layer (Streamlit)

- [ ] `startup_pitch/streamlit_app.py`:
  - Главный экран: кнопки `[Goalkeeper]` `[Striker]` `[Reaction Test]` `[Custom]`
  - Live view (embed cv2-окна или кадры из RTSP)
  - Live-метрики: текущая цель, статус пушки, last shot result
  - Session report: отражено/пропущено, среднее время реакции, график прогресса
- [ ] Один bash-скрипт `startup_pitch/run_demo.sh` поднимает всё (cameras → pipeline → launcher → UI).

### 3.2 Метрики игрока (не системы)

- [ ] Вместо perf_jsonl — `session_<timestamp>.json`:
  - `shots_fired`, `shots_blocked` (детектится по смене траектории мяча после контакта с телом)
  - `avg_reaction_time_ms`
  - `accuracy_by_zone` (на какие зоны попадает / парирует)
- [ ] Экспорт сессии в PDF (reportlab или weasyprint).

### 3.3 Safety hardening для внешнего деплоя

- [ ] Физический **E-stop на кабеле** (грибок) — параллельно программному
- [ ] **Сетевая изоляция**: airgapped по умолчанию; если сеть клиента открыта — HMAC на UDP (только тогда!)
- [ ] Guard rail: `max_pitch_clamp=25°` (вместо 30°) для демо с детьми — на 5° ниже, чем в S4

**Exit criteria:** неподготовленный человек (тренер) может запустить демо по инструкции на одном листе A4.

---

## Phase 4 — Outreach и пилот (2–3 месяца)

**Срок:** недели 5–12 после защиты
**Цель:** получить первого клиента (пилотная установка или grant).

### 4.1 Legal / юр. форма

- [ ] Решить: ТОО или ИП в РК? Для grant-денег обычно надо ТОО.
- [ ] IP: подать на утилитарную модель / полезную модель в Казпатент (быстрее патента, 1–3 месяца)
  - Claim: method + apparatus for pose-guided ballistic targeting
  - Это единственный defensibility-asset для инвестора

### 4.2 Cold outreach

- [ ] Академия Кайрата — через LinkedIn / email тренерского штаба
- [ ] ФК «Астана» академия — отдельный контакт
- [ ] Национальная команда U17/U19 — через KFF
- [ ] Спорт-теч фонды в РК: Astana Hub, QazTech Ventures

**Скрипт outreach-письма (один шаблон):**
> «Добрый день, [имя]. Я [имя], MSc в Nazarbayev University. Я разработал автоматический тренажёр для [вратарей/полевых] — пушка с компьютерным зрением, которая видит игрока и попадает в конкретную часть тела. Precision 4.4 мм, 200 ударов в час. Видео 60 сек: [ссылка]. Можем встретиться на 30 минут показать в живую? Я привезу установку.»

### 4.3 Пилот

- [ ] Бесплатная 2-недельная установка в одной академии (договориться на доступ + отзыв + видео)
- [ ] Собрать usage data → улучшить product-market fit
- [ ] На основе пилота — paid contract или равити-раунд

**Exit criteria:** подписан либо (a) первый платный контракт, либо (b) grant-финансирование, либо (c) convertible note от ангела.

---

## Phase 5 — Scale (отсрочка)

**Запускается только если Phase 4 дала деньги.**

Только здесь начинают работать «enterprise» советы из suggestions.md:

- [ ] Второй спорт (теннис / баскетбол) → Pipeline+Strategy становится оправдан
- [ ] Второй разработчик → убивается весь дубль, вводится `core/` + `adapters/`
- [ ] Вторая инсталляция → per-site YAML config обязателен
- [ ] MLflow + drift detection → при >3 арен
- [ ] ROS2 миграция — **только** если продукт пойдёт в mobile robotics (пушка на колёсах). Для fixed-install не нужен.

---

## Что НЕ делать ни в одной фазе

- **Rust / Zenoh** — чистое резюме-порно.
- **Digital twin с SMT-verification** — overkill даже для medical devices.
- **Formal верификация** — нет.
- **Hexagonal / DDD / CQRS** — пока у тебя 1 разработчик и 1 спорт, это вред.
- **Batch SVD / numba** — запас латенси 3×, зачем.
- **ROS2 до Phase 5** — 3–4 недели работы за нулевой выигрыш.

---

## Ключевые цифры для защиты и питча

(используй эти формулировки, не меняй на ходу)

| Метрика | Значение | Для кого |
|---|---|---|
| Pose-to-aim latency | ~50 мс | Thesis + питч |
| Precision (post-correction) | 4.4 мм | **Питч** (продающая цифра) |
| Accuracy (mean error raw) | 156–179 мм | Thesis (честно) |
| Accuracy (post-correction) | ~20–30 мм est. | Питч |
| FPS | 15 | Обоим |
| Safety layers | 10 | **Питч** (критично) |
| Setup time | ~30 минут | Питч |
| Cost per install (BOM) | ~$X | Питч |

*Посчитай BOM до Phase 2, это обязательно спросят.*

---

## Немедленный следующий шаг

**Завтра (2026-04-15):**
1. Закончить Phase 0 — ball tuning в лабе + запись чистого тестового прогона.
2. Если останется время — ball speed calibration (30–40 мин).

После этого — Phase 1.1 (common.py + ArenaConfig) в спокойные 2 часа перед защитой.
