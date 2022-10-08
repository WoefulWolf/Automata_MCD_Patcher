import copy
import os, sys
import json
import ioUtils
import zlib

def hash_event_name(name):
    return zlib.crc32(name.lower().encode("utf-8")) & ~0x80000000 # HAH gotem platinum

# https://github.com/synspawacza/nier_automata_localization
def calc_eager_padding(offset, mod): 
    return mod - (offset % mod)

def write_eager_padding(offset, mod):
    return b"\0" * calc_eager_padding(offset, mod)

class Header:
    struct_size = 40

    def from_mcd(self, file):
        self.messages_offset = ioUtils.read_int32(file)
        self.messages_count = ioUtils.read_int32(file)
        self.symbols_offset = ioUtils.read_int32(file)
        self.symbols_count = ioUtils.read_int32(file)
        self.glyphs_offset = ioUtils.read_int32(file)
        self.glyphs_count = ioUtils.read_int32(file)
        self.fonts_offset = ioUtils.read_int32(file)
        self.fonts_count = ioUtils.read_int32(file)
        self.events_offset = ioUtils.read_int32(file)
        self.events_count = ioUtils.read_int32(file)

        return self

    def write_file(self, file):
        ioUtils.write_Int32(file, self.messages_offset)
        ioUtils.write_Int32(file, self.messages_count)
        ioUtils.write_Int32(file, self.symbols_offset)
        ioUtils.write_Int32(file, self.symbols_count)
        ioUtils.write_Int32(file, self.glyphs_offset)
        ioUtils.write_Int32(file, self.glyphs_count)
        ioUtils.write_Int32(file, self.fonts_offset)
        ioUtils.write_Int32(file, self.fonts_count)
        ioUtils.write_Int32(file, self.events_offset)
        ioUtils.write_Int32(file, self.events_count)

class Line:
    struct_size = 24

    def from_mcd(self, file):
        content_offset = ioUtils.read_int32(file)
        self.padding = ioUtils.read_int32(file)
        content_length = ioUtils.read_int32(file)
        ioUtils.read_int32(file)
        self.below = ioUtils.read_float(file)
        self.horiz = ioUtils.read_float(file)

        last_pos = file.tell()
        self.content = []
        file.seek(content_offset)
        for i in range(content_length):
            val = ioUtils.read_int16(file)
            if val < -32000:
                val = val & 0xFFFF
            self.content.append(val)
        file.seek(last_pos)

        return self

    def to_string(self, symbols_glyph_Dict, font):   # I stole this :) https://github.com/synspawacza/nier_automata_localization
        result = ""
        idx = 0
        while idx < len(self.content):
            char_id = self.content[idx]
            if char_id < 0x8000:
                result += symbols_glyph_Dict[char_id].char
                if symbols_glyph_Dict[char_id].font_id != font.id:
                    raise Exception("Font mismatch")
                idx += 2  # skip kerning
            elif char_id == 0x8001:
                result += " "
                #result += f"[SET_FONT:{self.content[idx+1]}]"
                idx += 2  # skip font id
            elif char_id == 0x8000:
                # text end
                idx += 1
            elif char_id == 0x8020:
                result += "<special:" + str(self.content[idx + 1]) + ">"
                idx += 2
            else:
                # using '<' and '>' for tagging - hopefully it doesn't break anything
                result += "<unknown:" + str(char_id)
                if idx + 1 < len(self.content):
                    result += ":" + str(self.content[idx + 1])
                result += ">"
                idx += 2  # skip kerning
        return result

    def from_string(self, string, symbols, font, kernings):
        self.content = []
        self.padding = 0
        self.below = 0
        self.horiz = 0
        for i, char in enumerate(string):
            if (char == " "):
                self.content.append(0x8001)
                self.content.append(font.id)
            else:
                for symbol in symbols:
                    if symbol.font_id != font.id:
                        continue
                    glyph_found = False
                    if symbol.char == char:
                        val = symbol.glyph_id
                        glyph_found = True
                        break
                self.below = font.below

                if not glyph_found:
                    raise Exception("Glyph not found in font " + str(font.id) + ": " + char)
                self.content.append(val)

                # Get next char
                if i + 1 < len(string):
                    next_char = string[i + 1]
                    combined = char + next_char
                    if combined in kernings[font.id]:
                        self.content.append(round(kernings[font.id][combined]["kerning_num"]))
                    else:
                        self.content.append(0)
                else:
                    self.content.append(0)

        self.content.append(0x8000)
        return self

class Text:
    struct_size = 20

    def from_mcd(self, file):
        lines_offset = ioUtils.read_int32(file)
        lines_count = ioUtils.read_int32(file)
        self.vpos = ioUtils.read_int32(file)
        self.hpos = ioUtils.read_int32(file)
        self.font = ioUtils.read_int32(file)

        last_pos = file.tell()
        self.lines = []
        file.seek(lines_offset)
        for i in range(lines_count):
            self.lines.append(Line().from_mcd(file))
        file.seek(last_pos)

        return self

    def from_json(self, json, symbols, fonts_dict, kernings):
        self.lines = []
        self.vpos = json["vpos"]
        self.hpos = json["hpos"]
        self.font = json["font"]
        split_lines = json["line"].split("\n")
        for line in split_lines:
            self.lines.append(Line().from_string(line, symbols, fonts_dict[self.font], kernings))

        return self

    def to_string(self, symbols_char_Dict, fonts_dict):
        return "\n".join([line.to_string(symbols_char_Dict, fonts_dict[self.font]) for line in self.lines])

class Message:
    struct_size = 16

    def from_mcd(self, file):
        texts_offset = ioUtils.read_int32(file)
        texts_count = ioUtils.read_int32(file)
        self.seq_number = ioUtils.read_int32(file)
        self.event_id = ioUtils.read_int32(file)

        return_pos = file.tell()
        self.texts = []
        file.seek(texts_offset)
        for i in range(texts_count):
            self.texts.append(Text().from_mcd(file))
        file.seek(return_pos)

        return self

    def from_json(self, json, seq_number, symbols, fonts_dict, kernings):
        self.seq_number = seq_number
        self.event_name = json["event_name"]
        self.event_id = hash_event_name(self.event_name)
        self.texts = []
        for text in json["texts"]:
            self.texts.append(Text().from_json(text, symbols, fonts_dict, kernings))

        return self

class Symbol:
    struct_size = 8

    def from_mcd(self, file):
        self.font_id = ioUtils.read_int16(file)
        self.char = file.read(2).decode("utf-16-le")
        self.glyph_id = ioUtils.read_int32(file)

        return self

class Event:
    struct_size = 40

    def from_mcd(self, file):
        self.id = ioUtils.read_int32(file)
        self.idx = ioUtils.read_int32(file)
        self.name = file.read(32).decode("utf-8").rstrip("\0")

        return self

    def from_message(self, name, message_idx):
        self.id = hash_event_name(name)
        self.idx = message_idx
        self.name = name

        return self

class Font:
    struct_size = 20

    def from_mcd(self, file):
        self.id = ioUtils.read_int32(file)
        self.width = ioUtils.read_float(file)
        self.height = ioUtils.read_float(file)
        self.below = ioUtils.read_float(file)
        self.horiz = ioUtils.read_float(file)

        return self

class MCD:
    def from_mcd(self, file):
        self.header = Header().from_mcd(file)

        file.seek(self.header.messages_offset)
        self.messages = []
        for i in range(self.header.messages_count):
            self.messages.append(Message().from_mcd(file))

        file.seek(self.header.symbols_offset)
        self.symbols = []
        for i in range(self.header.symbols_count):
            self.symbols.append(Symbol().from_mcd(file))

        # Imma just skip over glyphs for now
        file.seek(self.header.glyphs_offset)
        self.glyphs = file.read(self.header.glyphs_count * 40)

        file.seek(self.header.fonts_offset)
        self.fonts = []
        for i in range(self.header.fonts_count):
            self.fonts.append(Font().from_mcd(file))

        file.seek(self.header.events_offset)
        self.events = []
        for i in range(self.header.events_count):
            self.events.append(Event().from_mcd(file))

        self.generate_events_Dict()
        self.generate_fonts_Dict()
        self.generate_symbols_char_Dict()
        self.generate_symbols_glyph_Dict()
        self.generate_kernings()

        return self

    def generate_events_Dict(self):
        self.events_Dict = {}
        for event in self.events:
            self.events_Dict[event.id] = event

    def generate_symbols_char_Dict(self):
        self.symbols_char_Dict = {}
        for symbol in self.symbols:
            self.symbols_char_Dict[symbol.char] = symbol

    def generate_symbols_glyph_Dict(self):
        self.symbols_glyph_Dict = {}
        for symbol in self.symbols:
            self.symbols_glyph_Dict[symbol.glyph_id] = symbol

    def generate_fonts_Dict(self):
        self.fonts_Dict = {}
        for font in self.fonts:
            self.fonts_Dict[font.id] = font

    # This function is gonked
    def generate_kernings(self):
        self.kernings = {}
        for font in self.fonts:
            self.kernings[font.id] = {}

        for message in self.messages:
            for text in message.texts:
                font = self.fonts_Dict[text.font]
                for line in text.lines:
                    idx = 0
                    while idx < len(line.content):
                        val = line.content[idx]
                        if val < 0x8000:
                            char = self.symbols_glyph_Dict[val].char
                            kerning = line.content[idx+1]
                            if kerning != 0:
                                next_val = line.content[idx+2]
                                if next_val < 0x8000:
                                    next_char = self.symbols_glyph_Dict[next_val].char
                                    if char + next_char in self.kernings[font.id]:
                                        self.kernings[font.id][char + next_char]["kerning_num"] += kerning
                                        self.kernings[font.id][char + next_char]["count"] += 1
                                    else:
                                        self.kernings[font.id][char + next_char] = {
                                            "kerning_num": kerning,
                                            "count": 1
                                        }
                            idx += 2
                        elif val == 0x8001:
                            idx += 2
                        elif val == 0x8000:
                            idx += 2

        for font in self.kernings.keys():
            for kerning in self.kernings[font].keys():
                self.kernings[font][kerning]["kerning_num"] /= self.kernings[font][kerning]["count"]

        #with open("kernings.json", "w") as file:
        #    json.dump(self.kernings, file, indent=4)

    def update_from_json(self, json):
        # Events
        self.events = []
        for i, message in enumerate(json["messages"]):
            self.events.append(Event().from_message(message["event_name"], i))
        self.events.sort(key=lambda x: x.id)
        self.generate_events_Dict()

        # Messages
        self.messages = []
        seq_number = json["starting_seq_number"]
        for message in json["messages"]:
            self.messages.append(Message().from_json(message, seq_number, self.symbols, self.fonts_Dict, self.kernings))
            seq_number += 1

        # Header
        self.header.messages_count = len(self.messages)
        self.header.events_count = len(self.events)

    def to_json(self):
        json_data = {}
        json_data["starting_seq_number"] = self.messages[0].seq_number
        json_data["messages"] = []

        for msg in self.messages:
            json_data["messages"].append({
                "event_name": self.events_Dict[msg.event_id].name,
                "texts": []
            })
            for text in msg.texts:
                json_data["messages"][-1]["texts"].append({
                    "vpos": text.vpos,
                    "hpos": text.hpos,
                    "font": text.font,
                    "line": text.to_string(self.symbols_glyph_Dict, self.fonts_Dict)
                })

        json_data["fonts"] = []
        for font in self.fonts:
            json_data["fonts"].append({
                "id": font.id,
                "symbols": []
            })
            for symbol in self.symbols:
                if symbol.font_id == font.id:
                    json_data["fonts"][-1]["symbols"].append({
                        "char": symbol.char,
                        "glyph_id": symbol.glyph_id
                    })
        return json_data

    def write_file(self, file): # https://github.com/synspawacza/nier_automata_localization
        current_offset = Header.struct_size

        strings = []
        strings_offsets = []

        texts = []
        texts_offsets = []

        lines = []
        lines_offsets = []

        for message in self.messages:
            for text in message.texts:
                texts.append(text)
                for line in text.lines:
                    strings.append(line.content)
                    strings_offsets.append(current_offset)
                    current_offset += len(line.content) * 2
                    lines.append(line)
        current_offset += calc_eager_padding(current_offset, 4)

        # Update header offsets
        self.header.messages_offset = current_offset
        current_offset += self.header.messages_count * Message.struct_size
        current_offset += calc_eager_padding(current_offset, 4)

        for i in range(len(texts)):
            texts_offsets.append(current_offset + i * Text.struct_size)
        current_offset += len(texts) * Text.struct_size
        current_offset += calc_eager_padding(current_offset, 4)

        for i in range(len(lines)):
            lines_offsets.append(current_offset + i * Line.struct_size)
        current_offset += len(lines) * Line.struct_size
        current_offset += calc_eager_padding(current_offset, 4)

        self.header.symbols_offset = current_offset
        self.header.symbols_count = len(self.symbols)
        current_offset += self.header.symbols_count * Symbol.struct_size + 4

        self.header.glyphs_offset = current_offset
        current_offset += self.header.glyphs_count * 40 + 4

        self.header.fonts_offset = current_offset
        self.header.fonts_count = len(self.fonts)
        current_offset += self.header.fonts_count * Font.struct_size + 4

        self.header.events_offset = current_offset

        # Write header
        self.header.write_file(file)
        
        # Write strings
        for string in strings:
            for v in string:
                val = v
                if val < 0:
                    ioUtils.write_Int16(file, val)
                else:
                    ioUtils.write_uInt16(file, val)
        file.write(write_eager_padding(file.tell(), 4))

        # Write messages
        texts_offset_idx = 0
        for message in self.messages:
            texts_offset = texts_offsets[texts_offset_idx]
            texts_offset_idx += len(message.texts)
            ioUtils.write_uInt32(file, texts_offset)
            ioUtils.write_uInt32(file, len(message.texts))
            ioUtils.write_uInt32(file, message.seq_number)
            ioUtils.write_uInt32(file, message.event_id)
        file.write(write_eager_padding(file.tell(), 4))

        # Write texts
        lines_offset_idx = 0
        for text in texts:
            lines_offset = lines_offsets[lines_offset_idx]
            lines_offset_idx += len(text.lines)
            ioUtils.write_uInt32(file, lines_offset)
            ioUtils.write_uInt32(file, len(text.lines))
            ioUtils.write_uInt32(file, text.vpos)
            ioUtils.write_uInt32(file, text.hpos)
            ioUtils.write_uInt32(file, text.font)
        file.write(write_eager_padding(file.tell(), 4))

        # Write lines
        strings_idx = 0
        for line in lines:
            strings_offset = strings_offsets[strings_idx]
            strings_idx += 1
            ioUtils.write_uInt32(file, strings_offset)
            ioUtils.write_uInt32(file, line.padding)
            ioUtils.write_uInt32(file, len(line.content))
            ioUtils.write_uInt32(file, len(line.content))
            ioUtils.write_float(file, line.below)
            ioUtils.write_float(file, line.horiz)
        file.write(write_eager_padding(file.tell(), 4))

        # Write symbols
        for symbol in self.symbols:
            ioUtils.write_uInt16(file, symbol.font_id)
            ioUtils.write_utf16(file, symbol.char, 2)
            ioUtils.write_uInt32(file, symbol.glyph_id)
        file.write(write_eager_padding(file.tell(), 4))

        # Write glyphs
        file.write(self.glyphs)
        file.write(write_eager_padding(file.tell(), 4))

        # Write fonts
        for font in self.fonts:
            ioUtils.write_uInt32(file, font.id)
            ioUtils.write_float(file, font.width)
            ioUtils.write_float(file, font.height)
            ioUtils.write_float(file, font.below)
            ioUtils.write_float(file, font.horiz)
        file.write(write_eager_padding(file.tell(), 4))

        # Write events
        for event in self.events:
            ioUtils.write_uInt32(file, event.id)
            ioUtils.write_uInt32(file, event.idx)
            ioUtils.write_utf8(file, event.name, 32)

        
def mcd_to_json(mcd_file):
    with open(mcd_file, 'rb') as file:
        mcd = MCD().from_mcd(file)

    outfile = os.path.splitext(mcd_file)[0] + ".json"

    with open(outfile, "w") as f:
        json_data = mcd.to_json()
        json_str = json.dumps(json_data, indent=4)
        f.write(json_str)

    print("Wrote " + outfile)

def json_to_mcd(json_file, mcd_file):
    with open(mcd_file, 'rb') as file:
        mcd = MCD().from_mcd(file)

    #org_mcd = copy.deepcopy(mcd)
    mcd.update_from_json(json.load(open(json_file, "r")))

    outfile = os.path.splitext(json_file)[0] + ".mcd"
    with open(outfile, "wb") as file:
        mcd.write_file(file)

    print("Wrote " + outfile)

if __name__ == "__main__":
    in_file = sys.argv[1]

    in_file = os.path.normpath(in_file)
    in_file_ext = os.path.splitext(in_file)[1]

    if in_file_ext == ".mcd":
        mcd_to_json(in_file)
    
    if in_file_ext == ".json":
        if len(sys.argv) < 3:
            mcd_file = input("Please specify the MCD file to use as a base for fonts/glyphs:\n")
        else:
            mcd_file = sys.argv[2]

        mcd_file = mcd_file.replace('"', "")
        mcd_file = os.path.normpath(mcd_file)
        json_to_mcd(in_file, mcd_file)