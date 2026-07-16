import pytest

from anonymizer.copybook.xml_mapper import (CopybookMappingError,
                                            layout_from_xml,
                                            UnsupportedCopybookError)

CUSTOMER_XML = """
<copybook filename="customer.cpy">
  <item level="01" name="CUSTOMER-RECORD" position="1" storage-length="202">
    <item level="05" name="CUST-ID" position="1" storage-length="8" picture="9(08)" numeric="true"/>
    <item level="05" name="CUST-NAME" position="9" storage-length="30" picture="X(30)"/>
    <item level="05" name="CUST-PHONE" position="39" storage-length="12" picture="X(12)" occurs="2"/>
    <item level="05" name="CUST-BALANCE" position="63" storage-length="6" picture="S9(09)V99"
          numeric="true" signed="true" usage="computational-3"/>
    <item level="05" name="CUST-BRANCH-CODE" position="69" storage-length="2" picture="9(04)"
          numeric="true" usage="computational"/>
  </item>
</copybook>
"""

REDEFINES_XML = """
<copybook filename="r.cpy">
  <item level="01" name="REC" position="1" storage-length="10">
    <item level="05" name="RAW-DATE" position="1" storage-length="8" picture="9(08)" numeric="true" redefined="true"/>
    <item level="05" name="DATE-PARTS" position="1" storage-length="8" redefines="RAW-DATE">
      <item level="10" name="DP-YEAR" position="1" storage-length="4" picture="9(04)" numeric="true"/>
      <item level="10" name="DP-MMDD" position="5" storage-length="4" picture="9(04)" numeric="true"/>
    </item>
    <item level="05" name="REC-FILLER" position="9" storage-length="2" picture="X(02)"/>
  </item>
</copybook>
"""

ODO_XML = """
<copybook filename="odo.cpy">
  <item level="01" name="REC" position="1" storage-length="26">
    <item level="05" name="TXN-COUNT" position="1" storage-length="2" picture="9(02)" numeric="true"/>
    <item level="05" name="TXN-AMT" position="3" storage-length="8" picture="9(08)" numeric="true"
          occurs="3" occurs-min="0" depending-on="TXN-COUNT"/>
  </item>
</copybook>
"""

ODO_TAIL_XML = """
<copybook filename="bad.cpy">
  <item level="01" name="REC" position="1" storage-length="30">
    <item level="05" name="TXN-COUNT" position="1" storage-length="2" picture="9(02)" numeric="true"/>
    <item level="05" name="TXN-AMT" position="3" storage-length="8" picture="9(08)" numeric="true"
          occurs="3" occurs-min="0" depending-on="TXN-COUNT"/>
    <item level="05" name="TRAILER" position="27" storage-length="4" picture="X(04)"/>
  </item>
</copybook>
"""

GROUP_ODO_XML = """
<copybook filename="g.cpy">
  <item level="01" name="REC" position="1" storage-length="30">
    <item level="05" name="TXN-COUNT" position="1" storage-length="2" picture="9(02)" numeric="true"/>
    <item level="05" name="TXN-GROUP" position="3" storage-length="8" occurs="3" occurs-min="0"
          depending-on="TXN-COUNT">
      <item level="10" name="TXN-AMT" position="3" storage-length="4" picture="9(08)" numeric="true"/>
      <item level="10" name="TXN-DATE" position="7" storage-length="4" picture="9(08)" numeric="true"/>
    </item>
  </item>
</copybook>
"""

GROUP_OCCURS_XML = """
<copybook filename="go.cpy">
  <item level="01" name="REC" position="1" storage-length="16">
    <item level="05" name="TXN-GROUP" position="1" storage-length="8" occurs="2">
      <item level="10" name="TXN-AMT" position="1" storage-length="4" picture="9(08)" numeric="true"/>
      <item level="10" name="TXN-CODE" position="5" storage-length="4" picture="X(04)"/>
    </item>
  </item>
</copybook>
"""

NUMERIC_OVERRIDE_XML = """
<copybook filename="num.cpy">
  <item level="01" name="REC" position="1" storage-length="5">
    <item level="05" name="ZBAL" position="1" storage-length="5" picture="Z(05)" numeric="true"/>
  </item>
</copybook>
"""

MULTI_ODO_XML = """
<copybook filename="multi.cpy">
  <item level="01" name="REC" position="1" storage-length="36">
    <item level="05" name="CNT-A" position="1" storage-length="2" picture="9(02)" numeric="true"/>
    <item level="05" name="CNT-B" position="3" storage-length="2" picture="9(02)" numeric="true"/>
    <item level="05" name="ARR-A" position="5" storage-length="8" picture="9(08)" numeric="true"
          occurs="2" occurs-min="0" depending-on="CNT-A"/>
    <item level="05" name="ARR-B" position="21" storage-length="8" picture="9(08)" numeric="true"
          occurs="2" occurs-min="0" depending-on="CNT-B"/>
  </item>
</copybook>
"""

COUNTER_NOT_FOUND_XML = """
<copybook filename="missing.cpy">
  <item level="01" name="REC" position="1" storage-length="18">
    <item level="05" name="ARR" position="1" storage-length="8" picture="9(08)" numeric="true"
          occurs="2" occurs-min="0" depending-on="MISSING-COUNTER"/>
  </item>
</copybook>
"""


def test_leaf_offsets_and_types():
    layout = layout_from_xml(CUSTOMER_XML)
    assert layout.name == "CUSTOMER-RECORD"
    assert layout.record_length == 202
    by_name = {f.name: f for f in layout.leaves}
    assert by_name["CUST-ID"].offset == 0 and by_name["CUST-ID"].length == 8
    assert by_name["CUST-ID"].numeric and by_name["CUST-ID"].usage == "display"
    assert by_name["CUST-NAME"].offset == 8
    bal = by_name["CUST-BALANCE"]
    assert bal.usage == "comp-3" and bal.signed and bal.decimals == 2 and bal.total_digits == 11
    assert by_name["CUST-BRANCH-CODE"].usage == "comp"


def test_occurs_expansion():
    layout = layout_from_xml(CUSTOMER_XML)
    names = [f.name for f in layout.leaves]
    assert "CUST-PHONE(1)" in names and "CUST-PHONE(2)" in names
    by_name = {f.name: f for f in layout.leaves}
    assert by_name["CUST-PHONE(1)"].offset == 38
    assert by_name["CUST-PHONE(2)"].offset == 50


def test_redefines_are_overlays():
    layout = layout_from_xml(REDEFINES_XML)
    leaf_names = {f.name for f in layout.leaves}
    overlay_names = {f.name for f in layout.overlays}
    assert "RAW-DATE" in leaf_names
    assert "DP-YEAR" in overlay_names and "DP-MMDD" in overlay_names
    assert "DP-YEAR" not in leaf_names


def test_odo_captured():
    layout = layout_from_xml(ODO_XML)
    assert layout.odo is not None
    assert layout.odo.counter.name == "TXN-COUNT"
    assert layout.odo.element_length == 8
    assert layout.odo.max_count == 3
    assert layout.odo.array_offset == 2
    assert layout.record_length_for(1) == 10
    assert layout.record_length_for(3) == 26


def test_odo_with_trailing_fields_rejected():
    with pytest.raises(UnsupportedCopybookError):
        layout_from_xml(ODO_TAIL_XML)


def test_group_level_odo_rejected():
    with pytest.raises(UnsupportedCopybookError):
        layout_from_xml(GROUP_ODO_XML)


def test_group_occurs_suffixes_descendant_leaves():
    layout = layout_from_xml(GROUP_OCCURS_XML)
    by_name = {f.name: f for f in layout.leaves}
    assert "TXN-AMT(1)" in by_name and "TXN-AMT(2)" in by_name
    assert "TXN-CODE(1)" in by_name and "TXN-CODE(2)" in by_name
    assert by_name["TXN-AMT(1)"].offset == 0
    assert by_name["TXN-CODE(1)"].offset == 4
    assert by_name["TXN-AMT(2)"].offset == 8
    assert by_name["TXN-CODE(2)"].offset == 12
    names = [f.name for f in layout.leaves]
    assert len(names) == len(set(names))


def test_numeric_attribute_is_trusted_even_if_picture_unclassified():
    layout = layout_from_xml(NUMERIC_OVERRIDE_XML)
    by_name = {f.name: f for f in layout.leaves}
    assert by_name["ZBAL"].numeric is True


def test_multiple_distinct_odo_counters_rejected():
    with pytest.raises(UnsupportedCopybookError):
        layout_from_xml(MULTI_ODO_XML)


def test_odo_counter_not_found_raises_mapping_error():
    with pytest.raises(CopybookMappingError):
        layout_from_xml(COUNTER_NOT_FOUND_XML)


def test_record_length_for_returns_fixed_length_when_no_odo():
    layout = layout_from_xml(CUSTOMER_XML)
    assert layout.odo is None
    assert layout.record_length_for(1) == 202
    assert layout.record_length_for(99) == 202
