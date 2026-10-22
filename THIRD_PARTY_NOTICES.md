# Third-party notices

The FTIR Contamination Analyzer (by Ali Obeidat, MIT License) ships with spectra from the
following open sources. Each file names its source in its header lines.

## OpenFTIR (MIT License)

Used in `ftir_analyzer/data/library_openftir_atr.csv` (the 16 reference spectra), in the demo
files `examples/01_*` to `examples/05_*`, `examples/10_*` and `examples/12_*`, and in
`examples/library_demo/`. These are selected columns of `data/Sample_Spectra.csv` from
https://github.com/VAMpire29122004/OpenFTIR (some interpolated onto the library's wavenumbers).

```
Copyright (c) 2026 Viraj Ajay Mhetar

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Open Specy (CC BY 4.0)

Used in `examples/07_particle_on_filter.csv`, `examples/08_fibre_on_filter.csv`,
`examples/09_empty_spot_on_filter.csv` and `examples/11_second_fibre_on_filter.csv`. These are
measurements from the test data of the Open Specy package
(https://github.com/wincowgerDEV/OpenSpecy-package): `ftir_ldpe_soil.asp`, and three pixels of
`CA_tiny_map`. The files were renamed, and only the wavenumber and absorbance columns were kept.
Licence: Creative Commons Attribution 4.0, https://creativecommons.org/licenses/by/4.0/

> Cowger, W., Steinmetz, Z., Gray, A., Munno, K., Lynch, J., Hapich, H., Primpke, S., De Frond, H.,
> Rochman, C., Herodotou, O. (2021). Microplastic Spectral Classification Needs an Open Source
> Community: Open Specy to the Rescue! *Analytical Chemistry* 93(21), 7543–7548.

The test file `tests/data/openspecy_sample.rds` contains OpenFTIR spectra (MIT, above), stored in the
structure of an Open Specy library file so that the import can be tested.

## Open Specy library (CC BY 4.0), optional, not distributed

In extended mode the program downloads, on the user's computer, the Open Specy reference library
(the copy Open Specy's R package uses, https://d2jrxerjcsjhs7.cloudfront.net/, or https://osf.io/x7dpz/;
Creative Commons Attribution 4.0) or imports a copy the user downloaded, and
keeps a fab-relevant part of it in `records/openspecy/`. These spectra are not part of this project.
Every report that uses them names Open Specy and cites:

> Cowger, W., Steinmetz, Z., Gray, A., Munno, K., Lynch, J., Hapich, H., Primpke, S., De Frond, H.,
> Rochman, C., Herodotou, O. (2021). Microplastic Spectral Classification Needs an Open Source
> Community: Open Specy to the Rescue! *Analytical Chemistry* 93(21), 7543–7548.

## FasTEX-KCL textile fibre spectra (MIT License)

Used in `examples/library_demo/Nylon6_reference_fibre_collection.csv`: the row of sample
MTF_NYL_083 (Microtrace forensic fibre reference collection, PA 6) of
`ml_datasets/feature_matrix_raw_transmittance.csv` from https://github.com/reeha-parkar/FasTEX-KCL,
written as two columns (wavenumber, transmittance). Measured with a PerkinElmer Frontier FT-IR and a
single-reflection diamond ATR.

```
MIT License

Copyright (c) 2025 Reeha Parkar

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

The dataset is cited as asked by its authors:

> Parkar, R., Jain, A., Prendergast-Miller, M., Stanton, T., Sheridan, K., Gallidabino, M. (2025).
> A dataset of infrared (ATR-FTIR) spectra for textile fibres of natural and man-made origin.
> Mendeley Data. https://doi.org/10.17632/rx3fjgz96x

## Polystyrene film (public domain)

Used in `examples/06_PS_calibration_film_transmission.csv`. It is a transmission spectrum of
polystyrene film (PerkinElmer 1600) from the Chemistry Department, University of the West Indies
(Mona): the public-domain JCAMP-DX test file `dupdec1.jdx`, as distributed in the jcamp package
(https://github.com/nzhagen/jcamp).

## Inter typeface (SIL Open Font License 1.1)

`ftir_analyzer/assets/fonts/Inter-*`: Inter (Regular, Medium, SemiBold, Bold), Copyright (c) 2016
The Inter Project Authors (https://github.com/rsms/inter). Taken from the `inter-ui` package (4.1.1);
the WOFF2 files were unpacked to TrueType without changing the glyphs, and two WOFF2 files are
embedded in the HTML report. The full licence text is in `ftir_analyzer/assets/fonts/OFL-Inter.txt`.

## IBM Plex Mono typeface (SIL Open Font License 1.1)

`ftir_analyzer/assets/fonts/IBMPlexMono-*`: IBM Plex Mono (Regular, Medium), used for checksums and
file paths, Copyright © 2017 IBM Corp., with Reserved Font Name "Plex". Taken from the
`@ibm/plex-mono` package. The WOFF2 files were unpacked to TrueType without changing the glyphs.
The full licence text is in `ftir_analyzer/assets/fonts/OFL-IBM-Plex.txt`.

## Lucide icons (ISC License)

`ftir_analyzer/assets/icons/`: a selection of icons from Lucide (https://lucide.dev), Copyright
(c) Lucide Icons and Contributors. The full licence text is in
`ftir_analyzer/assets/icons/LICENSE-lucide.txt`. The app recolours them to the theme and draws them
with a slightly thinner line when it draws them.

## Python packages

The program uses numpy, pandas, scipy and matplotlib (BSD-style licences), plotly (MIT),
rdata (MIT, to read Open Specy files), jcamp (MIT, Nathan Hagen, to read JCAMP-DX files), brukeropus (MIT, Josh Duran, to read Bruker OPUS files) and PySide6 / Qt (LGPL v3). They are installed separately with `pip` and are not distributed with this
project. A report written by the program embeds plotly.js (MIT License, Copyright Plotly, Inc.), so
that its interactive figures work offline; the licence notice is kept at the top of the embedded
script.
