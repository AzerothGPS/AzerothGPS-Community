"""A client in another language than English keeps only its own language's localized files (Map.db2, AreaTable.db2):
the reader reads those where the enUS one isn't on disk. Found 2026-11-19 on a German client: `agps capitals` stopped
at Map.db2, "not in local storage"."""

from azerothgps.extract.casc import CascStorage


def storage(on_disk):
    """A CascStorage with only its maps: FileDataID 1 is localized (enUS and deDE), 2 the same in every language."""
    st = object.__new__(CascStorage)
    st.text_locale = "deDE"
    st._warned = False
    st.root = {1: b"enUS-ckey", 2: b"all-ckey"}
    st.root_installed = {1: b"deDE-ckey"}
    st.encoding = {b"enUS-ckey": b"enUS-ekey", b"deDE-ckey": b"deDE-ekey", b"all-ckey": b"all-ekey--"}
    st.index = {st.encoding[c][:9]: object() for c in on_disk}
    st.read_ckey = lambda ckey, zero_encrypted=False: ckey
    return st


def test_a_german_client_reads_its_own_languages_file():
    st = storage([b"deDE-ckey", b"all-ckey"])
    assert st.read(1) == b"deDE-ckey" and st.read(2) == b"all-ckey"


def test_the_english_file_first_where_it_is_on_disk():
    st = storage([b"enUS-ckey", b"deDE-ckey", b"all-ckey"])
    assert st.read(1) == b"enUS-ckey"
