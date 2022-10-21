# Automata_MCD_Patcher

## What is this
This is a small python script used to unpack/repack NieR:Automata MCD files, allowing one to modify/add content in the file.

## Usage
#### Unpack MCD to JSON
`mcd.py <mcd file> [output json file]`

#### Repack JSON to MCD
`mcd.py <json file> <base mcd file> [output mcd file]`

## Notes
- If no output file is specified, the input file name will be used with the appropriate extension.
- `<base mcd file>` is used as the base for fonts/glyphs used in the new mcd file. (I recommend passing the originally unpacked MCD file)
