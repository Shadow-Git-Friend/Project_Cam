# Y-axis validation report (arena_fixed)

- `Ymax`: `305.0` cm
- Expected:
  - `CamEast + IDs 20,16,19,17,18,21,22` near `Y≈0`
  - `CamWest + IDs 11,12,13,14,15,10,0` near `Y≈Ymax`

## Camera Y (cm)
- `CamEast`: `5`
- `CamWest`: `297`
- `CamNorth`: `110`
- `CamSouth`: `153`

## Tag average Y (cm)
- `ID0`: `297`
- `ID1`: `82.25`
- `ID2`: `236.25`
- `ID3`: `241`
- `ID4`: `235.25`
- `ID5`: `167.35`
- `ID6`: `176.75`
- `ID7`: `78.55`
- `ID8`: `51.75`
- `ID9`: `80.15`
- `ID10`: `305`
- `ID11`: `78.75`
- `ID12`: `305`
- `ID13`: `305`
- `ID14`: `305`
- `ID15`: `305`
- `ID16`: `3`
- `ID17`: `0`
- `ID18`: `0`
- `ID19`: `0`
- `ID20`: `3`
- `ID21`: `3.5`
- `ID22`: `3.5`
- `ID23`: `216.25`

## Checks
- `CamEast_near_zero`: `OK`
- `CamWest_near_ymax`: `OK`
- `ID20_near_zero`: `OK`
- `ID16_near_zero`: `OK`
- `ID19_near_zero`: `OK`
- `ID17_near_zero`: `OK`
- `ID18_near_zero`: `OK`
- `ID21_near_zero`: `OK`
- `ID22_near_zero`: `OK`
- `ID11_near_ymax`: `FAIL`
- `ID12_near_ymax`: `OK`
- `ID13_near_ymax`: `OK`
- `ID14_near_ymax`: `OK`
- `ID15_near_ymax`: `OK`
- `ID10_near_ymax`: `OK`
- `ID0_near_ymax`: `OK`

- Check pass ratio: `0.938`

## Notes
- `Dimensions_fixed.txt` keeps East-side `Y=0` convention.
- `Dimensions_mirrored_y.txt` is generated only as debug alternative.
- No source files in `garage_lab_combined` were modified.
