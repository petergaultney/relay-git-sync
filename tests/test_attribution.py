from attribution import AuthorResolver, GitAuthor, dominant_user, parse_author, parse_authors


def spans(*pairs):
    return [{"text": text, "client_id": 1, "user": user} for text, user in pairs]


def test_parse_author():
    assert parse_author("Ada Lovelace <ada@example.com>") == GitAuthor(
        "Ada Lovelace", "ada@example.com"
    )
    assert parse_author("no email at all") is None
    assert parse_author("<just@email.com>") is None


def test_parse_authors_skips_malformed():
    parsed = parse_authors({"u1": "Ada <ada@example.com>", "u2": "nope"})
    assert list(parsed) == ["u1"]


def test_dominant_user_single_insertion():
    old = "hello world"
    new = "hello brave world"
    assert dominant_user(old, new, spans(("hello ", "ada"), ("brave ", "bob"), ("world", "ada"))) == "bob"


def test_dominant_user_picks_majority_of_changed_chars():
    old = ""
    new = "aaaaaaaaaa" + "bb"
    assert dominant_user(old, new, spans(("aaaaaaaaaa", "ada"), ("bb", "bob"))) == "ada"


def test_dominant_user_deletion_only_is_none():
    old = "hello cruel world"
    new = "hello world"
    assert dominant_user(old, new, spans(("hello world", "ada"))) is None


def test_dominant_user_mismatched_spans_is_none():
    assert dominant_user("", "actual content", spans(("stale content", "ada"))) is None


def test_dominant_user_unmapped_users_is_none():
    assert dominant_user("", "xyz", spans(("xyz", None))) is None


def test_resolver_maps_user_to_configured_author():
    ada = GitAuthor("Ada", "ada@example.com")
    resolver = AuthorResolver(lambda resource: spans(("new stuff", "u1")), {"u1": ada})
    assert resolver.resolve(object(), "", "new stuff") == ada


def test_resolver_unconfigured_user_is_none():
    resolver = AuthorResolver(
        lambda resource: spans(("new stuff", "someone-else")),
        {"u1": GitAuthor("Ada", "ada@example.com")},
    )
    assert resolver.resolve(object(), "", "new stuff") is None


def test_resolver_fetch_failure_is_none():
    def boom(resource):
        raise RuntimeError("server down")

    resolver = AuthorResolver(boom, {"u1": GitAuthor("Ada", "ada@example.com")})
    assert resolver.resolve(object(), "", "anything") is None


def test_resolver_without_authors_never_fetches():
    def boom(resource):
        raise AssertionError("should not fetch")

    assert AuthorResolver(boom, {}).resolve(object(), "", "anything") is None
