"""
FTIR Contamination Analyzer - makes ftir_analyzer/data/structures.json

The 3D view shows a short model chain of each polymer. The shapes are worked out once, here, and only the
small result is shipped, so the program itself does not need RDKit.

For each material: a short chain written as SMILES, real 3D coordinates (RDKit: ETKDG, then the MMFF94 force
field), and of 60 shapes the straightest, because a stretched chain reads best. Then which bonds belong to which
band group, found with SMARTS patterns. The wavenumber ranges are the rows of data/band_table.csv.

These are models, not the sample: a short chain, one shape of many. Copolymers and families (a note says so)
are one representative chain. The CH3 groups that only close the two ends of a chain are not band groups, and a
range is kept for a shipped material only if its reference spectrum has a band there, so a bond never lights up
for a band that material does not show.

Run it again only when a material or a group changes:
    python -m pip install rdkit numpy
    python tools/make_structures.py

Short names used in this file:
    mol = an RDKit molecule    xyz = atom positions in angstrom    ranges = [(low, high) in cm-1]

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import csv
import json
from pathlib import Path

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.rdMolDescriptors import CalcMolFormula

OUT = Path(__file__).resolve().parent.parent / "ftir_analyzer" / "data" / "structures.json"
LIBRARY = OUT.with_name("library_openftir_atr.csv")
SMALLEST = 0.03                                                         # a band: at least this share of the tallest
FAMILY = "One representative chain: the real material varies."
RANDOM = "One representative chain: the real order of the units is random."

# name in the library -> (a short chain as SMILES, a note)
CHAINS = {
    "PE (high density)": ("CCCCCCCCCCCCCC", ""),
    "PP": ("CC(C)CC(C)CC(C)CC(C)C", ""),
    "PS": ("CC(c1ccccc1)CC(c1ccccc1)CC(c1ccccc1)C", ""),
    "PET": ("COC(=O)c1ccc(cc1)C(=O)OCCOC(=O)c1ccc(cc1)C(=O)OC", ""),
    "PBT": ("COC(=O)c1ccc(cc1)C(=O)OCCCCOC(=O)c1ccc(cc1)C(=O)OC", ""),
    "PMMA": ("CC(C)(C(=O)OC)CC(C)(C(=O)OC)CC(C)(C(=O)OC)C", ""),
    "PC": ("COC(=O)Oc1ccc(cc1)C(C)(C)c1ccc(cc1)OC(=O)OC", ""),
    "Nylon 6,6": ("CC(=O)NCCCCCCNC(=O)CCCCC(=O)NCCCCCCNC(C)=O", ""),
    "PVOH": ("CC(O)CC(O)CC(O)CC(O)C", ""),
    "PAN": ("CC(C#N)CC(C#N)CC(C#N)C", ""),
    "EVA (25% VA)": ("CCCCCC(OC(C)=O)CCCCCC(OC(C)=O)CCCC", RANDOM),
    "PLA": ("CC(OC(C)=O)C(=O)OC(C)C(=O)OC(C)C(=O)OC", ""),
    "PVC": ("CC(Cl)CC(Cl)CC(Cl)CC(Cl)C", ""),
    "PU": ("CCOC(=O)Nc1ccc(cc1)Cc1ccc(cc1)NC(=O)OCC", FAMILY),
    "EVOH (44% ethylene)": ("CCCC(O)CCCC(O)CCCC(O)CC", RANDOM),
    "PK (polyketone)": ("CCC(=O)CCC(=O)CCC(=O)CCC(=O)CC", ""),
    # the demo's lab references
    "Nylon 6": ("CC(=O)NCCCCCC(=O)NCCCCCC(=O)NC", ""),
    "ABS": ("CC(C#N)CC=CCCC(c1ccccc1)CC(C#N)C", RANDOM),
    "SAN": ("CC(c1ccccc1)CC(C#N)CC(c1ccccc1)C", RANDOM),
    "Cellulose acetate": ("COC1C(OC(C)=O)C(OC(C)=O)C(COC(C)=O)OC1OC", FAMILY),
    "Cotton": ("COC1C(O)C(O)C(OC2C(O)C(O)C(OC)C(CO)O2)OC1CO", "Cellulose, what cotton is made of."),
    # materials of the Open Specy references, by their material group
    "PEEK": ("COc1ccc(cc1)Oc1ccc(cc1)C(=O)c1ccc(cc1)OC", ""),
    "POM": ("COCOCOCOCOCOC", ""),
    "PVAc": ("CC(OC(C)=O)CC(OC(C)=O)CC(OC(C)=O)C", ""),
    "polyethers": ("COCCOCCOCCOCCOC", "Polyethylene glycol, one of this family."),
    "polyvinylpyrrolidones": ("CC(N1CCCC1=O)CC(N1CCCC1=O)CC(N1CCCC1=O)C", ""),
    "polyimide": ("CN1C(=O)c2cc3c(cc2C1=O)C(=O)N(c1ccc(cc1)Oc1ccc(cc1)C)C3=O", FAMILY),
    "polyethersulfones": ("COc1ccc(cc1)S(=O)(=O)c1ccc(cc1)OC", ""),
    "silicone": ("C[Si](C)(C)O[Si](C)(C)O[Si](C)(C)O[Si](C)(C)C", "PDMS, the most common silicone."),
    "fluoropolymer": ("FC(F)(F)C(F)(F)C(F)(F)C(F)(F)C(F)(F)C(F)(F)F", "PTFE, one of this family."),
    "polyphenylene sulfide": ("Cc1ccc(cc1)Sc1ccc(cc1)Sc1ccc(cc1)C", ""),
    "epoxy": ("CC(C)(c1ccc(OCC2CO2)cc1)c1ccc(OCC2CO2)cc1", "The usual resin unit (BADGE), before curing."),
    "natural rubber": ("CC(C)=CCCC(C)=CCCC(C)=CCCC(C)=CC", ""),
}

ETHER = "[#6:1]-[O;X2;!$(O[CX3]=O);!$(Oc);!$(O[Si]);!$([OH]):2]"
METHYL = {"PP", "PMMA", "PC", "EVA (25% VA)", "PLA", "Cellulose acetate", "PVAc", "natural rubber", "silicone"}   # CH3 in the chain
# (label, band ranges, pattern: the two mapped atoms of each match are one bond), first match of a bond wins
GROUPS = [
    ("C=O (amide)", [(1620, 1680)], "[C;$(C(=O)[#7;!$(N(C=O)C=O)]);!$(C(O)(=O)N):1]=[O:2]"),
    ("C=O (carbonate)", [(1740, 1795)], "[C;$(C(=O)(O)O):1]=[O:2]"),
    ("C=O (urethane)", [(1680, 1740)], "[C;$(C(=O)(O)N):1]=[O:2]"),
    ("C=O (imide)", [(1700, 1795)], "[C;$(C(=O)N(C=O)):1]=[O:2]"),
    ("C=O (aryl ketone)", [(1620, 1680)], "[C;$(C(=O)(c)c):1]=[O:2]"),
    ("C=O", [(1700, 1765)], "[C:1]=[O:2]"),
    ("Amide II", [(1500, 1560)], "[#7;$(N[H]):1]-[C;$(C=O):2]"),
    ("Ester C–O", [(1210, 1300)], "[C;$(C=O):1]-[O;X2:2]"),
    ("Aryl ether C–O", [(1210, 1300)], "[c:1]-[O;X2:2]"),
    ("Si–O–Si", [(1000, 1150)], "[Si:1]-[O:2]"),
    ("Si–CH₃", [(1250, 1270), (780, 820)], "[Si:1]-[CH3:2]"),
    ("C–F", [(1100, 1300)], "[C:1]-[F:2]"),
    ("C–O", [(1000, 1150)], ETHER),
    ("O–C (ester)", [(1000, 1150)], "[CX4:1]-[O;X2;$(OC=O):2]"),
    ("C–OH", [(1000, 1150)], "[#6:1]-[OH:2]"),
    ("O–H", [(3200, 3680)], "[OH:1]-[H:2]"),
    ("N–H", [(3250, 3350)], "[#7:1]-[H:2]"),
    ("C≡N", [(2220, 2260)], "[C:1]#[N:2]"),
    ("C=C", [(1620, 1680)], "[C:1]=[C:2]"),
    ("Ring C=C", [(1590, 1612), (1480, 1520)], "[c:1]:[c:2]"),
    ("Aromatic C–H", [(3000, 3110), (690, 760), (830, 900)], "[c:1]-[H:2]"),
    ("CH₃ bend", [(1365, 1390)], "[CH3:1]-[H:2]"),
    ("CH₂ rock", [(690, 760)], "[$([CH2]([CH2])[CH2]):1]-[H:2]"),
    ("CH₂/CH₃ bend", [(1430, 1480)], "[CH2,CH3:1]-[H:2]"),
    ("Aliphatic C–H", [(2840, 2995)], "[CX4:1]-[H:2]"),
]
SHARED = {"CH₃ bend", "CH₂ rock", "CH₂/CH₃ bend", "Aliphatic C–H", "Aromatic C–H", "Ester C–O", "Aryl ether C–O",
          "N–H", "Amide II"}       # the same bonds can show in several bands; the others keep a bond to themselves


def build(smiles):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    ids = list(AllChem.EmbedMultipleConfs(mol, 60, randomSeed=7))
    AllChem.MMFFOptimizeMoleculeConfs(mol, maxIters=4000)
    heavy = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() > 1]

    def spread(conformer):
        xyz = mol.GetConformer(conformer).GetPositions()[heavy]
        return float(((xyz - xyz.mean(0)) ** 2).sum(1).mean())
    xyz = mol.GetConformer(max(ids, key=spread)).GetPositions()
    xyz = xyz - xyz.mean(0)
    return mol, xyz @ np.linalg.svd(xyz)[2].T                           # the long axis along x


def reference_spectra():
    """The shipped reference spectra: (wavenumbers, {material: absorbance}); the file names each column."""
    lines = [line for line in LIBRARY.read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
    rows = list(csv.reader(lines))
    table = np.array(rows[1:], float)
    return table[:, 0], {name: table[:, i + 1] for i, name in enumerate(rows[0][1:])}


def has_band(wn, a, low, high):
    """True if the spectrum has a clear band between these wavenumbers."""
    a = a - np.nanmin(a)
    tops = np.flatnonzero((a[1:-1] > a[:-2]) & (a[1:-1] >= a[2:])) + 1
    return any(low - 10 <= wn[i] <= high + 10 and a[i] >= SMALLEST * np.nanmax(a) for i in tops)


def groups_of(mol, name, references):
    taken, groups = set(), {}
    wn, spectra = references
    for label, ranges, smarts in GROUPS:
        if label == "CH₃ bend" and name not in METHYL:
            continue
        if name in spectra:
            shown = [r for r in ranges if has_band(wn, spectra[name], *r)]
            ranges, wanted = shown, ranges
        pattern = Chem.MolFromSmarts(smarts)
        maps = {a.GetAtomMapNum(): a.GetIdx() for a in pattern.GetAtoms() if a.GetAtomMapNum()}
        bonds = []
        for match in mol.GetSubstructMatches(pattern, maxMatches=500, uniquify=False):
            bond = mol.GetBondBetweenAtoms(match[maps[1]], match[maps[2]])
            if bond is None or (bond.GetIdx() in taken and label not in SHARED) or bond.GetIdx() in bonds:
                continue
            bonds.append(bond.GetIdx())
        if bonds:
            taken.update(bonds)
            if name in spectra and len(ranges) < len(wanted):
                print(f"   {name}: no band of {label} at {[r for r in wanted if r not in ranges]}")
            if ranges:
                groups[label] = {"ranges": ranges, "bonds": sorted(bonds)}
    return groups


def main():
    out, references = {}, reference_spectra()
    for name, (smiles, note) in CHAINS.items():
        mol, xyz = build(smiles)
        bonds = [[b.GetBeginAtomIdx(), b.GetEndAtomIdx(), 1.5 if b.GetIsAromatic() else b.GetBondTypeAsDouble()]
                 for b in mol.GetBonds()]
        atoms = [[a.GetSymbol(), *[round(float(v), 2) for v in p]] for a, p in zip(mol.GetAtoms(), xyz)]
        out[name] = {"formula": CalcMolFormula(mol), "smiles": smiles, "note": note, "atoms": atoms, "bonds": bonds,
                     "groups": groups_of(mol, name, references)}
        print(f"{name:24s} {out[name]['formula']:14s} {len(atoms):3d} atoms  " + ", ".join(out[name]["groups"]))
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT.name}: {OUT.stat().st_size // 1024} KB, {len(out)} materials")


if __name__ == "__main__":
    main()
