**Техническое задание на оказание услуг/выполнение работ**

| Наименование услуги/работы | Единицы измерения | Объем | Оценочная стоимость услуг | Место оказания услуг/выполнения работ | Срок оказания услуг/выполнения работ |
|---|---|---:|---|---|---|
| Промышленная камера **HikRobot MV-CS016-10GC (Color)** или эквивалент согласно характеристикам ниже | шт. | 6 | 1 001 128 тенге<br>(6 × 341 $ по курсу 489,31 тенге за 1 у.е.) | г. Астана, пр-кт Кабанбай батыра, 53 | 1 месяц |
| Объектив **HikRobot MVL-HF03524M-MP, 3.5 mm C-mount** или эквивалент согласно характеристикам ниже | шт. | 6 | 352 303 тенге<br>(6 × 120 $ по курсу 489,31 тенге за 1 у.е.) | г. Астана, пр-кт Кабанбай батыра, 53 | 1 месяц |
| Сетевая карта **Intel I350-T4, 4× RJ45 1GbE, PCIe x4** или эквивалент | шт. | 2 | 58 717 тенге<br>(2 × 60 $ по курсу 489,31 тенге за 1 у.е.) | г. Астана, пр-кт Кабанбай батыра, 53 | 1 месяц |
| Твердотельный накопитель **NVMe SSD 2 ТБ, M.2 2280** | шт. | 1 | 97 862 тенге<br>(200 $ по курсу 489,31 тенге за 1 у.е.) | г. Астана, пр-кт Кабанбай батыра, 53 | 1 месяц |
| Интерфейсный кабель камеры **HikRobot MV-ACC-01-2101-5m/10m, Hirose 6-pin/open-end** или эквивалент | шт. | 6 | 278 907 тенге<br>(6 × 95 $ по курсу 489,31 тенге за 1 у.е.) | г. Астана, пр-кт Кабанбай батыра, 53 | 1 месяц |
| Кабель Ethernet **Cat6 RJ45, pure copper, 5–10 m** | шт. | 6 | 29 359 тенге<br>(6 × 10 $ по курсу 489,31 тенге за 1 у.е.) | г. Астана, пр-кт Кабанбай батыра, 53 | 1 месяц |
| Комплект питания и синхронизации **12 V DC PSU + Line0 trigger distribution** | комплект | 1 | 24 466 тенге<br>(50 $ по курсу 489,31 тенге за 1 у.е.) | г. Астана, пр-кт Кабанбай батыра, 53 | 1 месяц |

### Обязательные технические характеристики и критерии приемки

**1. Промышленные камеры, 6 шт.**

- Рекомендуемая точная модель: **HikRobot MV-CS016-10GC**, цветная версия (**GC / Color**). Монохромная версия **MV-CS016-10GM** не является заменой без письменного согласования с инициатором.
- Сенсор: CMOS **global shutter**, Sony IMX296 или эквивалент, размер сенсора не менее 1/2.9", pixel size около 3.45 µm.
- Разрешение: не менее **1440 × 1080**.
- Частота кадров: не менее **60 fps** при полном разрешении; для MV-CS016-10GC — 65.2 fps @ 1440 × 1080.
- Интерфейс данных: **Gigabit Ethernet**, совместимость с **GigE Vision 2.0** и **GenICam**. USB-webcam, USB2-camera или rolling-shutter camera не допускаются.
- Формат пикселей: color Bayer 8/10/12 bit или RGB/BGR output. Цветная камера обязательна для дальнейшей детекции мяча/мишеней.
- Синхронизация: аппаратный trigger input, предпочтительно **opto-isolated input Line0** через 6-pin Hirose/P7 connector. Все 6 камер должны поддерживать одновременную внешнюю экспозицию от одного trigger pulse.
- Питание: 9–24 VDC и/или PoE. Если камеры подключаются напрямую к Intel I350-T4, учитывать, что сетевая карта не подает PoE; питание должно подаваться через MV-ACC power/I/O cable или через отдельные PoE injectors.
- Объективный интерфейс: **C-mount**, не CS-mount и не M12/S-mount.
- ПО: поддержка Windows/Linux; предпочтительно HikRobot MVS SDK и/или third-party GigE Vision software.
- Комплектность: каждая камера должна иметь индивидуальный серийный номер, MAC address, dust cap, warranty, datasheet. Все 6 камер должны быть одинаковой модели и ревизии, насколько это доступно у поставщика.

**2. Объективы C-mount, 6 шт.**

- Рекомендуемая точная модель: **HikRobot MVL-HF03524M-MP**.
- Тип: industrial FA lens, **C-mount**, flange focal distance 17.526 mm, совместимый с камерами C-mount.
- Фокусное расстояние: **3.5 mm preferred**. Допустимый диапазон эквивалента: **3.5–4.0 mm** только если подтверждено поле зрения; **6 mm не допускается** как основной объектив, потому что он слишком узкий для текущей арены.
- Размер изображения / sensor format: не менее **1/1.8"**. Это больше, чем 1/2.9" сенсор камеры, поэтому снижает риск виньетирования.
- Светосила: максимальная диафрагма **F2.4 или лучше**; F1.4–F2.4 допустимо. Для быстрого мяча нужна короткая экспозиция, поэтому темные объективы не подходят.
- Управление: ручной focus и manual iris; locking screws / фиксация фокуса и диафрагмы предпочтительны для стационарного монтажа.
- Distortion: низкая дисторсия; для MVL-HF03524M-MP заявлено около -1.23%. Эквивалент должен иметь distortion ≤2% или поставщик должен предоставить distortion data.
- Minimum working distance: ≤0.20 m; для MVL-HF03524M-MP — 0.15 m.
- Ожидаемое поле зрения на сенсоре 1/2.9" (примерно): при 3.5 mm — horizontal ~71°, vertical ~56°, diagonal ~83°. При 4.0 mm поле зрения меньше, поэтому 4.0 mm допускается только после проверки размещения.
- Не допускаются: CCTV varifocal lenses без lock, fisheye lens, M12/S-mount lens, CS-mount lens без корректного адаптера, объективы с неизвестным sensor coverage.

**3. Сетевые карты, 2 шт.**

- Рекомендуемая модель: **Intel I350-T4**.
- Минимум: 4 independent 1GbE RJ45 copper ports per card, PCIe x4 electrical interface, Linux driver support, Intel i350 controller or genuine equivalent.
- Назначение: 6 камер должны подключаться к ПК через выделенные Gigabit Ethernet ports. Один общий 1GbE switch на все камеры не допускается для full-rate capture; switch допустим только при uplink ≥10GbE и отдельном согласовании.
- Комплектность: full-height bracket; low-profile bracket желательно; новые или проверенные refurbished адаптеры с гарантией.
- Не допускаются: USB-to-Ethernet adapters, Realtek low-cost multiport adapters без проверки, fake/clone I350 cards без подтверждаемого Intel controller.

**4. NVMe SSD, 1 шт.**

- Форм-фактор: M.2 2280 NVMe.
- Объем: **2 TB**. 1 TB допустим только для коротких тестов; для 6 камер raw 60 fps 1 TB быстро заполнится.
- Интерфейс: PCIe Gen3 x4 или лучше.
- Sustained sequential write: не менее **1 000 MB/s**, желательно ≥1 500 MB/s.
- Endurance: желательно ≥600 TBW, TLC NAND preferred.
- Обоснование: 6× 1440×1080 Bayer8 @ 60 fps требуют примерно 560 MB/s raw write bandwidth до учета overhead. Накопитель должен иметь запас по sustained write, а не только peak write.
- Не допускаются: SATA M.2 SSD, QLC low-end SSD без sustained write guarantee, внешние USB SSD как основной диск записи.

**5. Power/I/O кабели камеры, 6 шт.**

- Рекомендуемая модель: **HikRobot MV-ACC-01-2101-5m** или **MV-ACC-01-2101-10m**.
- Тип: camera-side **Hirose 6-pin**, host-side open-end, power + digital I/O.
- Назначение: подача 9–24 VDC питания на камеру и подключение trigger input **Line0** / output Line1 / configurable Line2 согласно pinout камеры.
- Длина: 5–10 m для текущего гаража; если поставщик предлагает другую длину, согласовать до заказа.
- Требование к поставщику: предоставить pinout/цвета проводов и подтвердить совместимость именно с MV-CS016-10GC.

**6. Ethernet кабели, 6 шт.**

- Category: Cat6 или лучше, RJ45-RJ45, factory terminated.
- Длина: 5–10 m, с запасом для монтажа.
- Материал: **pure copper**, не CCA (copper-clad aluminium).
- Скорость: стабильный 1000BASE-T / 1GbE link на каждой камере.
- Предпочтительно: гибкая оболочка, маркировка кабелей 1–6, strain relief.

**7. Комплект питания и синхронизации, 1 комплект.**

- Power supply: regulated 12 V DC, минимум 60 W / 5 A. Рекомендуется 12 V 8–10 A для запаса, распределения питания и потерь в кабеле.
- Power distribution: отдельные линии питания на 6 камер, screw terminals, fuse или resettable protection per camera line preferred.
- Trigger board: вход от ESP32/TTL 3.3–5 V или другого controller, 6 synchronized outputs to camera Line0. Выходы должны быть совместимы с opto-isolated camera inputs.
- Trigger pulse: simultaneous exposure trigger для всех камер; pulse width configurable, ориентир 10 µs–10 ms.
- Electrical safety: общая земля/опорная схема должна соответствовать camera manual; питание камер не смешивать с питанием моторов/BLM launcher.
- Если поставщик предлагает PoE вместо 12 V wiring, требуется включить 6× IEEE 802.3af PoE injectors или эквивалентную схему питания, но trigger cables всё равно обязательны для Line0.

### Общие требования к поставке

- Поставщик должен указать точные part numbers в коммерческом предложении: camera body, lens, power/I/O cable, NIC, SSD, Ethernet cables, power/sync kit.
- Эквивалентные позиции допускаются только если они соответствуют всем минимальным требованиям выше и согласованы инициатором до закупки.
- К поставке приложить datasheets, warranty information, сертификаты/декларации соответствия при наличии, pinout кабелей, invoice/packing list.
- Гарантия: не менее 12 месяцев, если иное не согласовано.
- Все оборудование должно быть новым, без следов эксплуатации, если refurbished явно не согласован письменно.
- При приемке проверить: модель камеры **MV-CS016-10GC Color**, 6 одинаковых камер, объективы **3.5 mm C-mount**, наличие 6 power/I/O cables, 6 Cat6 cables, работоспособность 1GbE link, внешнего trigger mode и MVS/GigE Vision discovery.

| Параметр | Значение |
|---|---|
| Цель закупки | Приобретение оборудования для проведения научных исследований и разработки программного обеспечения в рамках проекта Project_Cam / Proxiball 3D. Оборудование нужно для синхронной многокамерной 3D-реконструкции движения человека, мяча и зоны попадания/отскока. |
| График оказания услуг/выполнения работ | Единовременная закупка оборудования. Онлайн-покупка у поставщика и/или местная IT-розница г. Астана. Срок поставки: 1 месяц. |
| Стоимость услуг/работ | 1 842 742 тенге (3 766 $ по курсу 489,31 тенге за 1 у.е.) |
| Специальные квалификационные требования к потенциальному поставщику | Специальная лицензия не требуется. Поставщик должен предоставить коммерческое предложение с точными part numbers, datasheets и подтверждением совместимости позиций. |
| Характеристика услуг/работ | Тип использования: академический / научно-исследовательский. Поставка оборудования, совместимого с industrial machine vision, external hardware trigger и Linux/GigE Vision workflow. |
| Результаты оказания услуг/выполнения работ | Поставленное оборудование, документация, гарантия, кабельные pinouts, подтверждение совместимости и комплектность согласно техническим характеристикам. |

**Справочные ссылки для проверки поставщиком**

- HikRobot MV-CS016-10GM/GC datasheet: <https://www.maxxvision.com/downloads/Cameras/GigE/Hikrobot/Hikrobot_MV-CS016-10GMGC.pdf>
- HikRobot MVL-HF03524M-MP lens datasheet: <https://www.hikrobotics.com/cn2/source/vision/document/2023/9/14/MVL-HF03524M-MP_20230831.pdf>
- HikRobot MV-ACC-01-2101-x power/I/O cable datasheet: <https://multipix.com/wp-content/uploads/2020/06/MV-ACC-01-2101-x_en_20191111.pdf>
- Intel I350-T4 specifications: <https://www.intel.com/content/www/us/en/products/sku/184824/intel-ethernet-network-adapter-i350t4-for-ocp-3-0/specifications.html>

Инициатор

Ассистент Профессор Арзыкулов Султангали Усенбатырович

*(должность) (подпись, дата) (Ф.И.О.)*

\newpage

**Terms of reference for the provision of services / performance of work**

| Service / work name | Units | Amount | Estimated cost of services | Place of provision of services / performance of work | Service / performance term |
|---|---|---:|---|---|---|
| Industrial camera **HikRobot MV-CS016-10GC (Color)** or equivalent according to specifications below | units | 6 | KZT 1,001,128<br>(6 × $341 at the rate of 489.31 KZT per 1 USD) | Astana, Kabanbay Batyr avenue, 53 | 1 month |
| Lens **HikRobot MVL-HF03524M-MP, 3.5 mm C-mount** or equivalent according to specifications below | units | 6 | KZT 352,303<br>(6 × $120 at the rate of 489.31 KZT per 1 USD) | Astana, Kabanbay Batyr avenue, 53 | 1 month |
| Network adapter **Intel I350-T4, 4× RJ45 1GbE, PCIe x4** or equivalent | units | 2 | KZT 58,717<br>(2 × $60 at the rate of 489.31 KZT per 1 USD) | Astana, Kabanbay Batyr avenue, 53 | 1 month |
| Solid-state drive **NVMe SSD 2 TB, M.2 2280** | units | 1 | KZT 97,862<br>($200 at the rate of 489.31 KZT per 1 USD) | Astana, Kabanbay Batyr avenue, 53 | 1 month |
| Camera interface cable **HikRobot MV-ACC-01-2101-5m/10m, Hirose 6-pin/open-end** or equivalent | units | 6 | KZT 278,907<br>(6 × $95 at the rate of 489.31 KZT per 1 USD) | Astana, Kabanbay Batyr avenue, 53 | 1 month |
| Ethernet cable **Cat6 RJ45, pure copper, 5–10 m** | units | 6 | KZT 29,359<br>(6 × $10 at the rate of 489.31 KZT per 1 USD) | Astana, Kabanbay Batyr avenue, 53 | 1 month |
| Power and synchronization kit **12 V DC PSU + Line0 trigger distribution** | set | 1 | KZT 24,466<br>($50 at the rate of 489.31 KZT per 1 USD) | Astana, Kabanbay Batyr avenue, 53 | 1 month |

### Mandatory technical specifications and acceptance criteria

**1. Industrial cameras, 6 units.**

- Recommended exact model: **HikRobot MV-CS016-10GC**, color version (**GC / Color**). The monochrome **MV-CS016-10GM** is not an acceptable substitute without written approval by the initiator.
- Sensor: CMOS **global shutter**, Sony IMX296 or equivalent, sensor size at least 1/2.9", pixel size approximately 3.45 µm.
- Resolution: at least **1440 × 1080**.
- Frame rate: at least **60 fps** at full resolution; MV-CS016-10GC provides 65.2 fps @ 1440 × 1080.
- Data interface: **Gigabit Ethernet**, compatible with **GigE Vision 2.0** and **GenICam**. USB webcams, USB2 cameras, and rolling-shutter cameras are not accepted.
- Pixel format: color Bayer 8/10/12 bit or RGB/BGR output. Color cameras are required for future ball/target detection.
- Synchronization: external hardware trigger input, preferably **opto-isolated input Line0** through the 6-pin Hirose/P7 connector. All 6 cameras must support simultaneous external exposure from one trigger pulse.
- Power: 9–24 VDC and/or PoE. If cameras are connected directly to Intel I350-T4 adapters, the adapters do not supply PoE; power must be supplied via the MV-ACC power/I/O cable or via separate PoE injectors.
- Lens mount: **C-mount**, not CS-mount and not M12/S-mount.
- Software: Windows/Linux support; HikRobot MVS SDK and/or third-party GigE Vision software support preferred.
- Completeness: each camera must include serial number, MAC address, dust cap, warranty, and datasheet. All 6 cameras should be the same model and hardware revision where available.

**2. C-mount lenses, 6 units.**

- Recommended exact model: **HikRobot MVL-HF03524M-MP**.
- Type: industrial FA lens, **C-mount**, 17.526 mm flange focal distance, compatible with C-mount industrial cameras.
- Focal length: **3.5 mm preferred**. Equivalent acceptable range: **3.5–4.0 mm** only if field of view is confirmed; **6 mm is not accepted** as the primary lens because it is too narrow for the current arena.
- Image size / sensor format: at least **1/1.8"**, which is larger than the camera 1/2.9" sensor and reduces vignetting risk.
- Aperture: maximum aperture **F2.4 or faster**; F1.4–F2.4 is acceptable. A bright lens is required for short exposure of a fast ball.
- Controls: manual focus and manual iris; focus/iris locking screws are preferred for fixed installation.
- Distortion: low distortion; MVL-HF03524M-MP is specified around -1.23%. Equivalent lenses must provide distortion data and should be ≤2%.
- Minimum working distance: ≤0.20 m; MVL-HF03524M-MP is 0.15 m.
- Expected field of view on a 1/2.9" sensor: approximately horizontal ~71°, vertical ~56°, diagonal ~83° at 3.5 mm. At 4.0 mm the field of view is narrower, so 4.0 mm must be approved after layout check.
- Not accepted: CCTV varifocal lenses without locks, fisheye lenses, M12/S-mount lenses, CS-mount lenses without correct adapter, and lenses with unknown sensor coverage.

**3. Network adapters, 2 units.**

- Recommended model: **Intel I350-T4**.
- Minimum: four independent 1GbE RJ45 copper ports per card, PCIe x4 electrical interface, Linux driver support, Intel i350 controller or genuine equivalent.
- Purpose: the 6 cameras must connect to the PC through dedicated Gigabit Ethernet ports. One shared 1GbE switch for all cameras is not acceptable for full-rate capture; a switch is acceptable only with ≥10GbE uplink and prior approval.
- Completeness: full-height bracket; low-profile bracket preferred; new or verified refurbished adapters with warranty.
- Not accepted: USB-to-Ethernet adapters, unverified low-cost Realtek multiport adapters, and fake/clone I350 cards without a verifiable Intel controller.

**4. NVMe SSD, 1 unit.**

- Form factor: M.2 2280 NVMe.
- Capacity: **2 TB**. 1 TB is acceptable only for short tests; it is not preferred for 6-camera raw capture.
- Interface: PCIe Gen3 x4 or better.
- Sustained sequential write: at least **1,000 MB/s**, preferably ≥1,500 MB/s.
- Endurance: preferably ≥600 TBW, TLC NAND preferred.
- Reason: 6× 1440×1080 Bayer8 @ 60 fps requires approximately 560 MB/s raw write bandwidth before overhead. The drive must have sustained write headroom, not only peak write speed.
- Not accepted: SATA M.2 SSD, low-end QLC SSD without sustained write guarantee, and external USB SSD as the primary recording drive.

**5. Camera Power/I/O cables, 6 units.**

- Recommended model: **HikRobot MV-ACC-01-2101-5m** or **MV-ACC-01-2101-10m**.
- Type: camera-side **Hirose 6-pin**, host-side open-end, power + digital I/O.
- Purpose: provide 9–24 VDC camera power and connect trigger input **Line0** / output Line1 / configurable Line2 according to the camera pinout.
- Length: 5–10 m for the current garage; other lengths must be approved before order.
- Supplier requirement: provide pinout/wire colors and confirm compatibility specifically with MV-CS016-10GC.

**6. Ethernet cables, 6 units.**

- Category: Cat6 or better, RJ45-RJ45, factory terminated.
- Length: 5–10 m, with spare length for mounting.
- Material: **pure copper**, not CCA.
- Link speed: stable 1000BASE-T / 1GbE link for each camera.
- Preferred: flexible jacket, cable labels 1–6, strain relief.

**7. Power and synchronization kit, 1 set.**

- Power supply: regulated 12 V DC, minimum 60 W / 5 A. Recommended 12 V 8–10 A for headroom, power distribution, and cable losses.
- Power distribution: separate power lines to 6 cameras, screw terminals, fuse or resettable protection per camera line preferred.
- Trigger board: input from ESP32/TTL 3.3–5 V or another controller, 6 synchronized outputs to camera Line0. Outputs must be compatible with opto-isolated camera inputs.
- Trigger pulse: simultaneous exposure trigger for all cameras; configurable pulse width, target range 10 µs–10 ms.
- Electrical safety: grounding/common reference must follow the camera manual; camera power must not be mixed with motor/BLM launcher power.
- If the supplier proposes PoE instead of 12 V wiring, include 6× IEEE 802.3af PoE injectors or an equivalent power scheme; trigger cables are still mandatory for Line0.

### General delivery requirements

- The supplier must state exact part numbers in the commercial offer: camera body, lens, power/I/O cable, NIC, SSD, Ethernet cables, power/synchronization kit.
- Equivalent items are accepted only if they meet all minimum requirements above and are approved by the initiator before purchase.
- Delivery must include datasheets, warranty information, certificates/declarations where available, cable pinouts, invoice/packing list.
- Warranty: at least 12 months unless otherwise agreed.
- All equipment must be new and unused unless refurbished status is explicitly approved in writing.
- Acceptance checks: camera model **MV-CS016-10GC Color**, 6 matching cameras, **3.5 mm C-mount** lenses, 6 power/I/O cables, 6 Cat6 cables, working 1GbE links, external trigger mode, and MVS/GigE Vision discovery.

| Parameter | Value |
|---|---|
| Purpose of the purchase | Purchase of equipment for scientific research and software development within the Project_Cam / Proxiball 3D project. The equipment is required for synchronized multi-camera 3D reconstruction of human motion, ball motion, and target/bounce area events. |
| Service / work schedule | One-time hardware purchase. Online purchase from supplier and/or local IT retail in Astana. Delivery term: 1 month. |
| Cost of services / works | KZT 1,842,742 (USD 3,766 at the rate of 489.31 KZT per 1 USD) |
| Special qualification requirements for a potential supplier | No special license is required. The supplier must provide a commercial offer with exact part numbers, datasheets, and compatibility confirmation. |
| Description of services / works | Type of use: academic / research. Delivery of equipment compatible with industrial machine vision, external hardware trigger, and Linux/GigE Vision workflow. |
| Results of the provision of services / performance of work | Delivered equipment, documentation, warranty, cable pinouts, compatibility confirmation, and completeness according to the technical specifications. |

**Reference links for supplier verification**

- HikRobot MV-CS016-10GM/GC datasheet: <https://www.maxxvision.com/downloads/Cameras/GigE/Hikrobot/Hikrobot_MV-CS016-10GMGC.pdf>
- HikRobot MVL-HF03524M-MP lens datasheet: <https://www.hikrobotics.com/cn2/source/vision/document/2023/9/14/MVL-HF03524M-MP_20230831.pdf>
- HikRobot MV-ACC-01-2101-x power/I/O cable datasheet: <https://multipix.com/wp-content/uploads/2020/06/MV-ACC-01-2101-x_en_20191111.pdf>
- Intel I350-T4 specifications: <https://www.intel.com/content/www/us/en/products/sku/184824/intel-ethernet-network-adapter-i350t4-for-ocp-3-0/specifications.html>

Initiator

Assistant Professor Sultangali Arzykulov

*(position) (signature, date) (Name)*

\newpage

**Қызмет көрсету/жұмысты орындау бойынша техникалық тапсырма**

| Қызмет/жұмыс атауы | Өлшем бірлігі | Көлемі | Қызметтердің болжамды құны | Қызмет көрсету/жұмысты орындау орны | Қызметтерді көрсету/жұмыстарды орындау ұзақтығы |
|---|---|---:|---|---|---|
| **HikRobot MV-CS016-10GC (Color)** өнеркәсіптік камерасы немесе төмендегі сипаттамаға сәйкес баламасы | дана | 6 | 1 001 128 теңге<br>(6 × 341 $ 1 АҚШ доллары үшін 489,31 теңге бағамында) | Астана қ., Қабанбай батыр даңғылы, 53 | 1 ай |
| **HikRobot MVL-HF03524M-MP, 3.5 mm C-mount** объективі немесе төмендегі сипаттамаға сәйкес баламасы | дана | 6 | 352 303 теңге<br>(6 × 120 $ 1 АҚШ доллары үшін 489,31 теңге бағамында) | Астана қ., Қабанбай батыр даңғылы, 53 | 1 ай |
| **Intel I350-T4, 4× RJ45 1GbE, PCIe x4** желілік картасы немесе баламасы | дана | 2 | 58 717 теңге<br>(2 × 60 $ 1 АҚШ доллары үшін 489,31 теңге бағамында) | Астана қ., Қабанбай батыр даңғылы, 53 | 1 ай |
| **NVMe SSD 2 TB, M.2 2280** қатты күйлі диск | дана | 1 | 97 862 теңге<br>(200 $ 1 АҚШ доллары үшін 489,31 теңге бағамында) | Астана қ., Қабанбай батыр даңғылы, 53 | 1 ай |
| Камера интерфейс кабелі **HikRobot MV-ACC-01-2101-5m/10m, Hirose 6-pin/open-end** немесе баламасы | дана | 6 | 278 907 теңге<br>(6 × 95 $ 1 АҚШ доллары үшін 489,31 теңге бағамында) | Астана қ., Қабанбай батыр даңғылы, 53 | 1 ай |
| Ethernet кабелі **Cat6 RJ45, pure copper, 5–10 m** | дана | 6 | 29 359 теңге<br>(6 × 10 $ 1 АҚШ доллары үшін 489,31 теңге бағамында) | Астана қ., Қабанбай батыр даңғылы, 53 | 1 ай |
| Қуат және синхрондау жинағы **12 V DC PSU + Line0 trigger distribution** | жинақ | 1 | 24 466 теңге<br>(50 $ 1 АҚШ доллары үшін 489,31 теңге бағамында) | Астана қ., Қабанбай батыр даңғылы, 53 | 1 ай |

### Міндетті техникалық сипаттамалар және қабылдау талаптары

**1. Өнеркәсіптік камералар, 6 дана.**

- Ұсынылатын нақты модель: **HikRobot MV-CS016-10GC**, color version (**GC / Color**). **MV-CS016-10GM** monochrome version тек бастамашының жазбаша келісімімен ғана балама бола алады.
- Сенсор: CMOS **global shutter**, Sony IMX296 немесе баламасы, sensor size кемінде 1/2.9", pixel size шамамен 3.45 µm.
- Resolution: кемінде **1440 × 1080**.
- Frame rate: full resolution кезінде кемінде **60 fps**; MV-CS016-10GC үшін 65.2 fps @ 1440 × 1080.
- Data interface: **Gigabit Ethernet**, **GigE Vision 2.0** және **GenICam** compatible. USB webcam, USB2 camera және rolling-shutter camera қабылданбайды.
- Pixel format: color Bayer 8/10/12 bit немесе RGB/BGR output.
- Synchronization: external hardware trigger input, preferably **opto-isolated input Line0** through 6-pin Hirose/P7 connector. 6 камера бір trigger pulse арқылы synchronized exposure қолдауы тиіс.
- Power: 9–24 VDC және/немесе PoE. Intel I350-T4 direct connection кезінде network card PoE бермейді; power MV-ACC cable немесе separate PoE injectors арқылы берілуі тиіс.
- Lens mount: **C-mount**, CS-mount және M12/S-mount емес.
- Software: Windows/Linux support; HikRobot MVS SDK және/немесе GigE Vision third-party software support.

**2. C-mount объективтер, 6 дана.**

- Ұсынылатын нақты модель: **HikRobot MVL-HF03524M-MP**.
- Type: industrial FA lens, **C-mount**, 17.526 mm flange focal distance.
- Focal length: **3.5 mm preferred**. Балама диапазон **3.5–4.0 mm** тек field of view расталған жағдайда; **6 mm негізгі объектив ретінде қабылданбайды**, себебі current arena үшін тым тар.
- Image size / sensor format: кемінде **1/1.8"**, camera sensor 1/2.9" өлшемінен үлкен.
- Aperture: **F2.4 немесе жарығырақ**; F1.4–F2.4 acceptable.
- Controls: manual focus және manual iris; fixed installation үшін locking screws preferred.
- Distortion: low distortion; equivalent lens distortion data беруі тиіс және ≤2% болғаны жөн.
- Minimum working distance: ≤0.20 m.
- 1/2.9" sensor үшін expected field of view: 3.5 mm кезінде horizontal ~71°, vertical ~56°, diagonal ~83°.
- Қабылданбайды: CCTV varifocal lens without locks, fisheye lens, M12/S-mount lens, CS-mount lens without correct adapter, unknown sensor coverage lens.

**3. Желілік карталар, 2 дана.**

- Ұсынылатын модель: **Intel I350-T4**.
- Minimum: each card has 4 independent 1GbE RJ45 copper ports, PCIe x4 electrical interface, Linux driver support, Intel i350 controller немесе genuine equivalent.
- 6 камера PC-ға dedicated Gigabit Ethernet ports арқылы қосылуы тиіс. Бір ортақ 1GbE switch барлық камера үшін full-rate capture-ге қабылданбайды.
- Қабылданбайды: USB-to-Ethernet adapters, unverified low-cost multiport adapters, fake/clone I350 cards.

**4. NVMe SSD, 1 дана.**

- Form factor: M.2 2280 NVMe.
- Capacity: **2 TB**.
- Interface: PCIe Gen3 x4 немесе жоғары.
- Sustained sequential write: кемінде **1 000 MB/s**, preferably ≥1 500 MB/s.
- Endurance: preferably ≥600 TBW, TLC NAND preferred.
- Reason: 6× 1440×1080 Bayer8 @ 60 fps approximately 560 MB/s raw write bandwidth қажет етеді.
- Қабылданбайды: SATA M.2 SSD, low-end QLC SSD without sustained write guarantee, external USB SSD as primary recording drive.

**5. Camera Power/I/O cables, 6 дана.**

- Ұсынылатын модель: **HikRobot MV-ACC-01-2101-5m** немесе **MV-ACC-01-2101-10m**.
- Type: camera-side **Hirose 6-pin**, host-side open-end, power + digital I/O.
- Purpose: 9–24 VDC camera power және trigger input **Line0** connection.
- Length: 5–10 m.
- Supplier pinout/wire colors және MV-CS016-10GC compatibility confirmation беруі тиіс.

**6. Ethernet cables, 6 дана.**

- Category: Cat6 немесе жоғары, RJ45-RJ45, factory terminated.
- Length: 5–10 m.
- Material: **pure copper**, CCA емес.
- Link speed: each camera үшін stable 1000BASE-T / 1GbE link.

**7. Power and synchronization kit, 1 set.**

- Power supply: regulated 12 V DC, minimum 60 W / 5 A; recommended 12 V 8–10 A.
- Power distribution: 6 камераға separate power lines, screw terminals, protection preferred.
- Trigger board: ESP32/TTL 3.3–5 V input, 6 synchronized outputs to camera Line0.
- Trigger pulse: all cameras үшін simultaneous exposure trigger, configurable pulse width 10 µs–10 ms.
- Camera power motor/BLM launcher power-мен араластырылмауы тиіс.
- PoE ұсынылса, 6× IEEE 802.3af PoE injectors немесе equivalent power scheme қажет; Line0 trigger cables бәрібір міндетті.

### Жеткізуге қойылатын жалпы талаптар

- Supplier commercial offer ішінде exact part numbers көрсетуі тиіс: camera body, lens, power/I/O cable, NIC, SSD, Ethernet cables, power/synchronization kit.
- Equivalent items only if all minimum requirements are met and approved before purchase.
- Delivery includes datasheets, warranty information, certificates/declarations where available, cable pinouts, invoice/packing list.
- Warranty: кемінде 12 ай, unless otherwise agreed.
- Equipment new and unused unless refurbished explicitly approved in writing.
- Acceptance checks: **MV-CS016-10GC Color**, 6 matching cameras, **3.5 mm C-mount** lenses, 6 power/I/O cables, 6 Cat6 cables, working 1GbE links, external trigger mode, and MVS/GigE Vision discovery.

| Параметр | Мәні |
|---|---|
| Сатып алу мақсаты | Project_Cam / Proxiball 3D жобасы аясында ғылыми зерттеулер жүргізу және бағдарламалық жасақтаманы әзірлеу үшін жабдық сатып алу. Жабдық human motion, ball motion және target/bounce area events үшін synchronized multi-camera 3D reconstruction жасауға қажет. |
| Қызметтерді көрсету/жұмыстарды орындау кестесі | Бір реттік жабдық сатып алу. Жеткізушіден онлайн сатып алу және/немесе Астана қаласының жергілікті IT-дүкендері. Жеткізу мерзімі: 1 ай. |
| Қызметтердің/жұмыстардың құны | 1 842 742 теңге (3 766 $ 1 АҚШ доллары үшін 489,31 теңге бағамында) |
| Әлеуетті өнім берушіге қойылатын арнайы біліктілік талаптары | Арнайы лицензия талап етілмейді. Supplier exact part numbers, datasheets және compatibility confirmation бар commercial offer беруі тиіс. |
| Қызметтердің/жұмыстардың сипаттамасы | Қолдану түрі: академиялық / ғылыми-зерттеу. Industrial machine vision, external hardware trigger және Linux/GigE Vision workflow compatible equipment delivery. |
| Қызмет көрсету/жұмыстарды орындау нәтижелері | Delivered equipment, documentation, warranty, cable pinouts, compatibility confirmation, and completeness according to technical specifications. |

**Supplier verification reference links**

- HikRobot MV-CS016-10GM/GC datasheet: <https://www.maxxvision.com/downloads/Cameras/GigE/Hikrobot/Hikrobot_MV-CS016-10GMGC.pdf>
- HikRobot MVL-HF03524M-MP lens datasheet: <https://www.hikrobotics.com/cn2/source/vision/document/2023/9/14/MVL-HF03524M-MP_20230831.pdf>
- HikRobot MV-ACC-01-2101-x power/I/O cable datasheet: <https://multipix.com/wp-content/uploads/2020/06/MV-ACC-01-2101-x_en_20191111.pdf>
- Intel I350-T4 specifications: <https://www.intel.com/content/www/us/en/products/sku/184824/intel-ethernet-network-adapter-i350t4-for-ocp-3-0/specifications.html>

Бастамашы

Ассистент профессор Арзықұлов Сұлтанғали Үсенбатырұлы __________________

*(лауазымы) (Т.А.Ә.) (күні, қолы)*
