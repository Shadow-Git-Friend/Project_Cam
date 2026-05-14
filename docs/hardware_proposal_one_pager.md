# Project_Cam — Hardware Upgrade Proposal (Path B)

**Author:** Hanush · **Date:** 2026-05-11 · **Page:** 1 / 1

## Проблема
Текущая точность системы 95–180 мм mean, P95 до 290 мм. Это **не подходит для биомеханического screening и публикации**. Причина — не алгоритмы, а железо: **rolling shutter + 15 FPS + software sync + неконтролируемое освещение**. Эти четыре фактора съедают 20–30% точности каждый. Без их устранения validation paper будет слабым и не откроет jumps / sprints / cuts.

## Решение: Path B (рекомендованный) — $4,030

| Компонент | Цена | Что чинит | Почему именно это |
|---|---:|---|---|
| 4× FLIR Blackfly S USB3 `BFS-U3-16S2C-CS` (Sony IMX273, global shutter, 60+ FPS, hardware trigger) | $2,800 | Motion blur, rolling-shutter geometry distortion, FPS bottleneck | Industry-standard в биомеханике (Theia3D, OpenCap, Move.ai используют FLIR или эквивалент). Hardware trigger = sync jitter < 10 µs vs ~3 ms сейчас. |
| 4× Computar M0814-MP2 8mm C-mount lenses | $480 | Стабильная резкость, фиксированный фокус | Покрывает арену 6 м, manual iris не дрейфит между сессиями. |
| GPIO sync кабель + FLIR breakout | $150 | Software-sync drift (300× улучшение) | Без hardware sync global shutter теряет смысл. Один TTL импульс триггерит все 4 камеры одновременно. |
| 2× LED panel 100 W high-CRI (Godox SL150II / Aputure Amaran 100x) | $600 | Освещение, motion blur, confidence variance | Theia рекомендует ≥1000 lux. Joint confidence поднимается на 8-12%. Самый дешёвый и быстрый ROI. |
| Mounts, cables, shipping, customs | ~$700 | Operational | |

## Дешёвые альтернативы (если бюджет узкий)

| Вариант | Цена | Что чинит | Когда брать |
|---|---:|---|---|
| Path A — только освещение | $900 | Lighting variance | Если профессор готов отдать $1k, не $4k. Свет даёт +10-15% к точности уже за неделю. |
| Path B Lite — 1 reference camera + свет | $1,550 | Освещение + одна точная камера для validation против остальных 3 | Если бюджет ~$2k и хочется начать reference-grade validation на одной камере. |
| Path B Used — used FLIR/Basler с eBay | $1,700–2,300 | Всё, но риск с used (sensor scratches, нет гарантии) | Если есть expertise на отладку used industrial cameras. |
| **Path B Full (рекомендован)** | **$4,030** | **Всё, low risk, документировано** | **Бюджет $4k+ → правильный выбор** |
| Path C — 8 cameras GigE | $7–10k | + покрытие, + production-grade | Только для full lab build, не нужно сейчас |

## Где заказать (от быстрого к медленному до Астаны)

| Источник | Что | Lead time |
|---|---|---|
| **AliExpress** (CN/EU склад) | LED panels (Godox, Aputure), C-mount lenses (Computar, Tamron), Arduino+транзисторы для DIY-sync | **7–14 дней** |
| **Wildberries KZ / Kaspi** | LED panels, tripods, mounts, USB3 кабели | **3–10 дней** |
| **Basler EU distributor** (Польша/Германия) | FLIR Blackfly или Basler ace через corporate PO | **2–4 недели** |
| **Edmund Optics** (US) | Computar lenses, FLIR breakout boards, research-grade сервис | **2–3 недели** + растаможка |
| **B&H Photo** (NYC) | Godox/Aputure напрямую, прозрачные цены | **2–3 недели** + customs ~10-15% |
| **Daheng Vision** (FLIR партнёр в Азии) | FLIR cameras с отгрузкой в КЗ | **~2 недели** |

**В Казахстане напрямую** machine-vision камер FLIR/Basler **нет**. Но **LED, кабели и Arduino — заказывать локально** (быстрее на 1-2 недели).

## Рекомендованный план действий

| Неделя | Действие | Стоимость на неделе |
|---|---|---|
| **Эта неделя** | Заказать 2× LED panels (Wildberries) + Arduino sync kit (AliExpress). Параллельно оформить corporate PO в NU procurement на FLIR через Basler EU distributor. | $650 |
| **Неделя 2** | LED + Arduino приехали → A/B тест точности со старым vs новым освещением. Промежуточные цифры до/после. | $0 |
| **Неделя 3-4** | FLIR + lenses + GPIO breakout приезжают → монтаж, intrinsics calibration, hardware sync verification (LED-flash test). | $3,380 |
| **Неделя 5** | Recording v2 fixtures (`*_v2.jsonl`) на новом железе → re-validate valgus thresholds, re-tune confidence gates. | $0 |

## Что отвечать на возражения

- **"Почему не Kinect / RealSense?"** Depth-сенсоры дают 10 мм точности только до 4 м в идеальных условиях. Наша арена 6.2 м, multi-view triangulation. Несовместимо.
- **"Почему не GoPro?"** Rolling shutter, нет hardware trigger. Move.ai компенсирует огромным ML-датасетом которого у нас нет.
- **"Можем взять камеры из лаборатории NU?"** Если у Robotics Lab / ECE есть Sony RX0 II или подобные с hardware sync — отлично, проверим. Иначе купить дешевле чем мучиться с consumer hardware.
- **"global shutter не критичен для squat"** Согласен, для squat можно вытерпеть rolling shutter. Но как только заявляем jumps / sprints — rolling shutter дисквалифицирует. Path A ($900) достаточно если scope строго `только squat`.

## Bottom line

> **Path A ($900)** = свет, +15% качества за неделю. Хороший proof-of-concept перед основной тратой.
> **Path B Full ($4,030)** = решает все 4 ограничения, открывает jumps/sprints, готовит validation paper. Lead time 3-4 недели.
> **Действие на этой неделе:** заказать $650 (свет + Arduino) сразу, параллельно оформить PO на FLIR. Через 2 недели — промежуточные результаты со светом до тратится основной бюджет.
