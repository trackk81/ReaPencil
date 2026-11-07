import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reatoon.brush_profiles import flat_linear_value
from reatoon.ascii_brush_profiles import parse_profiles,read_profiles
from reatoon import binary_brush_profiles as binary


def mb_chunk(tag,payload,opaque=b'\x96\x01\0\0'):
    pad=b'' if tag==b'FOR8' else b'\0'*((-len(payload))%8)
    return tag+opaque+struct.pack('>Q',len(payload))+payload+pad


def mb_group(kind,*children):return mb_chunk(b'FOR8',kind+b''.join(children),b'\0'*4)


class BinaryProfileTests(unittest.TestCase):
    uid='11223344-5566-7788-99aa-bbccddeeff00'

    def fixture(self,value=.25,kind=binary.BRUSH_DETAIL_TYPE):
        identity=b'\x80source\0'+struct.pack('<4I',0x11223344,0x55667788,0x99aabbcc,0xddeeff00)
        rows=(0,0,value,0,value,0,value,0,1,value,1,value,1,value)
        curve=b'srcps[0:1]\0\x24'+struct.pack('>14d',*rows)
        return mb_group(b'Maya',mb_group(kind,mb_chunk(b'CREA',identity),
            mb_chunk(b'FLGS',b'srcps\0\x2c'+struct.pack('>I',2)),mb_chunk(b'CMPD',curve)))

    def parse(self,data):return binary.parse_profiles(io.BytesIO(data),len(data))

    def test_uuid_word_order_alignment_and_big_endian_rows(self):
        result=self.parse(self.fixture())
        rows=result[self.uid]['srcps']
        self.assertEqual(rows[0],(0.,0.,.25,0.,.25,0.,.25))
        self.assertEqual(rows[1],(0.,1.,.25,1.,.25,1.,.25))
        self.assertEqual(self.parse(self.fixture(kind=b'MESH')),{})
        self.assertEqual(self.parse(self.fixture().replace(b'\x96\x01\0\0',b'D\x01\0\0')),result)

    def test_no_raw_signature_search_inside_unrelated_payloads(self):
        body=mb_group(b'Maya',mb_chunk(b'DATA',self.fixture()))
        self.assertEqual(self.parse(body),{})

    def test_geometry_payload_is_skipped_without_reading_or_allocating_it(self):
        data=mb_group(b'Maya',mb_chunk(b'DATA',b'ignored geometry'*150000),self.fixture()[20:])
        class CountingStream(io.BytesIO):
            total=0
            def read(self,n=-1):
                if n<0 or n>4096:raise AssertionError('Unexpected geometry payload read')
                result=super().read(n);self.total+=len(result);return result
        stream=CountingStream(data)
        self.assertIn(self.uid,binary.parse_profiles(stream,len(data)))
        self.assertLess(stream.total,4096)

    def test_corrupt_bounds_truncation_and_unknown_layout_rejected(self):
        data=self.fixture()
        for malformed in (data[:-1],data+b'\0',b'FOR4'+data[4:],data[:28]+b'\xff'*8+data[36:]):
            with self.assertRaises(ValueError):self.parse(malformed)

    def test_invalid_curve_encoding_is_not_guessed(self):
        for malformed in (b'srcps[0:1]\0\x24'+b'\0'*8,b'srcps[0]\0\x99'+b'\0'*56,
                          b'srcps[9000]\0\x24'+b'\0'*56,
                          b'srcps[0]\0\x24'+struct.pack('>7d',0,0,.25,0,float('nan'),0,.25)):
            self.assertIsNone(binary.decode_curve(malformed))

    def test_duplicate_node_identity_rejected(self):
        group=self.fixture()[20:]
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.parse(mb_group(b'Maya',group,group))

    def test_partial_array_or_scalar_override_is_not_silently_flattened(self):
        data=self.fixture()
        self.assertEqual(self.parse(data.replace(b'srcps\0\x2c\0\0\0\x02',b'srcps\0\x2c\0\0\0\x03')),{})
        # Append a child override to the actual node group, adjusting both
        # container lengths. Its mixed encoding is outside verified support.
        override=mb_chunk(b'DBLE',b'srcps[1].srcpy\0\x24'+struct.pack('>d',1.))
        node=data[40:]+override
        mixed=mb_group(b'Maya',mb_group(binary.BRUSH_DETAIL_TYPE,node))
        self.assertEqual(self.parse(mixed),{})

    def test_cache_tracks_binary_source_changes(self):
        import os
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'source.mb';p.write_bytes(self.fixture())
            first=binary.read_profiles(p);before=p.stat().st_mtime_ns
            p.write_bytes(self.fixture(.5));os.utime(p,ns=(before+1000000,before+1000000))
            self.assertNotEqual(first,binary.read_profiles(p))
            self.assertEqual(binary.read_profiles(Path(td)/'unsupported.ma'),{})


class ProfileTests(unittest.TestCase):
    def test_only_complete_constant_linear_curves_are_folded(self):
        for value in (0.,.25,.5,1.):
            self.assertEqual(flat_linear_value([(0,0,value),(0,1,value)]),value)
        for points in ([],[(0,0,.5)],[(0,0,.5),(0,1,.25)],[(2,0,.5),(0,1,.5)],
                       [(0,0,.5),(0,0,.5),(0,1,.5)],[(0,.1,.5),(0,1,.5)],
                       [(0,0,None),(0,1,.5)],[(0,0,float('nan')),(0,1,.5)],
                       [(0,0,1.1),(0,1,1.1)]):
            self.assertIsNone(flat_linear_value(points))

    def fixture(self,value='.25'):
        return ('createNode PencilBrushDetail -n "source";\n'
                'rename -uid "11111111-2222-3333-4444-555555555555";\n'
                'setAttr -s 2 ".srcps[0:1]" 0 0 '+value+' 0 '+value+' 0 '+value+
                ' 0 1 '+value+' 1 '+value+' 1 '+value+';\n')

    def test_ascii_uuid_rows_comments_and_quoted_script_content(self):
        fake=self.fixture('.9').replace('"','\\"')
        text='// header\ncreateNode script -n "ignored"; setAttr ".b" -type "string" "'+fake+'";\n'
        text+='/* fake; createNode PencilBrushDetail; */\n'+self.fixture()
        text+='createNode network -n "other"; setAttr ".srcps[0]" 0 0 1 0 1 0 1;'
        result=parse_profiles(io.StringIO(text))
        self.assertEqual(len(result),1)
        rows=result['11111111-2222-3333-4444-555555555555']['srcps']
        self.assertEqual(flat_linear_value([(p[0],p[3],p[4]) for p in rows.values()]),.25)

    def test_ascii_malformed_arrays_and_nonfinite_values_are_not_recovered(self):
        for text in (self.fixture('nan'),self.fixture('inf'),self.fixture().replace('[0:1]','[0:3]'),
                     self.fixture().replace('[0:1]','[9000:9001]'),self.fixture().replace('0 0 .25','0 0 bogus',1)):
            self.assertEqual(parse_profiles(io.StringIO(text)),{})

    def test_source_cache_observes_file_changes_and_rejects_binary_paths(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'source.ma';p.write_text(self.fixture(),encoding='utf8')
            first=read_profiles(p)
            p.write_text(self.fixture('.125'),encoding='utf8')
            second=read_profiles(p)
            self.assertNotEqual(first,second)
            self.assertEqual(read_profiles(Path(td)/'source.mb'),{})


if __name__=='__main__':unittest.main()
