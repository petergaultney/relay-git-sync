from attribution import AuthorResolver, GitAuthor, attributing_users, parse_author, parse_authors


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


def test_attributing_users_single_insertion():
    old = "hello world"
    new = "hello brave world"
    assert attributing_users(
        old, new, spans(("hello ", "ada"), ("brave ", "bob"), ("world", "ada"))
    ) == ["bob"]


def test_attributing_users_ordered_by_changed_chars():
    old = ""
    new = "aaaaaaaaaa" + "bb"
    assert attributing_users(old, new, spans(("aaaaaaaaaa", "ada"), ("bb", "bob"))) == [
        "ada",
        "bob",
    ]


def test_attributing_users_deletion_only_is_empty():
    old = "hello cruel world"
    new = "hello world"
    assert attributing_users(old, new, spans(("hello world", "ada"))) == []


def test_attributing_users_mismatched_spans_is_empty():
    assert attributing_users("", "actual content", spans(("stale content", "ada"))) == []


def test_attributing_users_unmapped_users_is_empty():
    assert attributing_users("", "xyz", spans(("xyz", None))) == []


def test_resolver_maps_users_to_configured_authors():
    ada = GitAuthor("Ada", "ada@example.com")
    resolver = AuthorResolver(lambda resource: spans(("new stuff", "u1")), {"u1": ada})
    assert resolver.resolve(object(), "", "new stuff") == [ada]


def test_resolver_orders_dominant_first_and_skips_unconfigured():
    ada = GitAuthor("Ada", "ada@example.com")
    bob = GitAuthor("Bob", "bob@example.com")
    resolver = AuthorResolver(
        lambda resource: spans(("bbbbbbbbbb", "u2"), ("aaa", "u1"), ("zz", "u3")),
        {"u1": ada, "u2": bob},
    )
    assert resolver.resolve(object(), "", "bbbbbbbbbbaaazz") == [bob, ada]


def test_resolver_unconfigured_user_is_empty():
    resolver = AuthorResolver(
        lambda resource: spans(("new stuff", "someone-else")),
        {"u1": GitAuthor("Ada", "ada@example.com")},
    )
    assert resolver.resolve(object(), "", "new stuff") == []


def test_resolver_fetch_failure_is_empty():
    def boom(resource):
        raise RuntimeError("server down")

    resolver = AuthorResolver(boom, {"u1": GitAuthor("Ada", "ada@example.com")})
    assert resolver.resolve(object(), "", "anything") == []


def test_resolver_without_authors_never_fetches():
    def boom(resource):
        raise AssertionError("should not fetch")

    assert AuthorResolver(boom, {}).resolve(object(), "", "anything") == []
