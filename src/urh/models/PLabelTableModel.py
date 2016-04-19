from PyQt5.QtCore import QAbstractTableModel, pyqtSignal, Qt, QModelIndex

from urh.signalprocessing.ProtocoLabel import ProtocolLabel
from urh.signalprocessing.ProtocolAnalyzer import ProtocolAnalyzer
from urh.signalprocessing.ProtocolGroup import ProtocolGroup


class PLabelTableModel(QAbstractTableModel):
    header_labels = ["Name", "Start", "End", 'Match exactly',
                     "Matching sequence", 'Color', 'Apply decoding', 'Delete']

    restrictive_changed = pyqtSignal(int, bool)
    label_removed = pyqtSignal(ProtocolLabel)

    def __init__(self, proto_group: ProtocolGroup, offset:int, parent=None):
        super().__init__(parent)
        self.row_count = len(proto_group.labels)
        self.proto_view = 0
        self.proto_group = proto_group
        self.protocol_labels = proto_group.labels
        self.offset = offset
        self.layoutChanged.emit()

    def update(self):
        self.protocol_labels = self.proto_group.labels
        self.row_count = len(self.protocol_labels)
        if self.row_count > 0:
            i1 = self.createIndex(0, 0)
            i2 = self.createIndex(self.row_count-1, len(self.header_labels)-1)
            self.dataChanged.emit(i1, i2)
        self.layoutChanged.emit()

    def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
        return len(self.header_labels)

    def rowCount(self, QModelIndex_parent=None, *args, **kwargs):
        return len(self.protocol_labels)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.header_labels[section]
        return super().headerData(section, orientation, role)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            i = index.row()
            j = index.column()
            lbl = self.protocol_labels[i]
            if j == 0:
                return lbl.name
            elif j == 1:
                return self.proto_group.get_label_range(lbl, self.proto_view, True)[0] + 1
            elif j == 2:
                return self.proto_group.get_label_range(lbl, self.proto_view, True)[1]
            elif j == 3:
                return lbl.restrictive
            elif j == 4:
                if lbl.restrictive:
                    start = int(self.proto_group.convert_index(lbl.start, 0, self.proto_view, True)[0])
                    end = int(self.proto_group.convert_index(lbl.end, 0, self.proto_view, True)[1])
                    block = self.proto_group.blocks[lbl.refblock]
                    if self.proto_view == 0:
                        return block.decoded_bits_str[start:end]
                    elif self.proto_view == 1:
                        return block.decoded_hex_str[start:end]
                    else:
                        return block.decoded_ascii_str[start:end]
                else:
                    return "-"
            elif j == 5:
                return lbl.color_index
            elif j == 6:
                return lbl.apply_decoding
        elif role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        else:
            return None

    def setData(self, index: QModelIndex, value, role=Qt.DisplayRole):
        if value == "":
            return True

        i = index.row()
        j = index.column()
        if i >= len(self.protocol_labels):
            return False

        lbl = self.protocol_labels[i]
        proto = self.proto_group.decoded_bits_str

        if j == 0:
            lbl.name = value
        elif j == 1:
            new_start = int(self.proto_group.convert_index(int(value) - 1, self.proto_view, 0, True, i)[0])
            lbl.start = new_start
            # lbl.refblock passt hier wahrscheinlich nicht
            lbl.reference_bits = proto[lbl.refblock][lbl.start:lbl.end]
            lbl.find_block_numbers(proto)
        elif j == 2:
            new_end = int(self.proto_group.convert_index(int(value) - 1, self.proto_view, 0, True, i)[1]) + 1
            lbl.end = new_end
            lbl.reference_bits = proto[lbl.refblock][lbl.start:lbl.end]
            lbl.find_block_numbers(proto)
        elif j == 3:
            lbl.restrictive = value
            lbl.reference_bits = proto[lbl.refblock][lbl.start:lbl.end]
            self.restrictive_changed.emit(i, value)
            lbl.find_block_numbers(proto)
        elif j == 4:
            # Pass Reference bits via seperate dialog
            pass
        elif j == 5:
            lbl.color_index = value
        elif j == 6:
            lbl.apply_decoding = bool(value)
        elif j == 7:
            self.remove_label(self.protocol_labels[i])

        return True

    def set_refblock(self, lbl: ProtocolLabel, refblock: int):
        proto = self.proto_group.decoded_bits_str
        lbl.refblock = int(refblock) - self.offset
        lbl.reference_bits = proto[lbl.refblock][lbl.start:lbl.end]
        lbl.find_block_numbers(proto)


    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        try:
            lbl = self.protocol_labels[index.row()]
        except IndexError:
            return Qt.NoItemFlags

        if index.column() == 4 and not lbl.restrictive:
            return Qt.NoItemFlags
        elif index.column() == 4 and lbl.restrictive:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled

        return Qt.ItemIsEditable | Qt.ItemIsEnabled

    def remove_label(self, label):
        self.proto_group.remove_label(label)
        self.update()
        self.label_removed.emit(label)

    def get_protocol_sequences(self, start: int, end: int):
        sequences = []
        indexes = []
        start = int(self.proto_group.convert_index(start, 0, self.proto_view, True)[0])
        end = int(self.proto_group.convert_index(end, 0, self.proto_view, True)[0])

        for i, block in enumerate(self.proto_group.blocks):

            if self.proto_view == 0:
                data = block.decoded_bits_str[start:end]
            elif self.proto_view == 1:
                data  = block.decoded_hex_str[start:end]
            else:
                data  = block.decoded_ascii_str[start:end]

            if len(data) == end - start and data not in sequences:
                sequences.append(data)
                indexes.append(i) # For setting refblock later

        return sequences, indexes
