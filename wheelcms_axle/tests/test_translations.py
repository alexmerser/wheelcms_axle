from wheelcms_axle.node import Node
from django.utils import translation
from django.conf import settings
import pytest

class TestRootNode(object):
    def setup(self):
        settings.LANGUAGES = ('en', 'nl', 'fr')
        settings.FALLBACK = False

    def test_disabled(self, client):
        """ multi language support disabled """
        pytest.skip("todo")

    def test_setup(self, client):
        translation.activate('en')
        root = Node.root()
        assert root.path == ''
        assert root.slug() == ''
        assert root.get_path('en') == ''
        assert root.get_path('nl') == ''
        assert root.get_path('fr') == ''

        assert root.slug('en') == ''
        assert root.slug('nl') == ''
        assert root.slug('fr') == ''

    def test_non_supported_language(self, client):
        """ a non-supported language, no fallback """
        translation.activate('de')
        root = Node.root()
        assert root is None

    def test_default(self, client):
        settings.FALLBACK = 'en'
        root = Node.root()
        assert root.path == ''

    ## root cannot be renamed

class TestNode(object):
    def setup(self):
        from django.conf import settings
        settings.LANGUAGES = ('en', 'nl', 'fr')

    def test_node(self, client):
        translation.activate('en')
        root = Node.root()
        child = root.add("child")
        en_child = Node.get("/child")
        assert en_child == child
        assert en_child.path == "/child"
        assert en_child.slug() == "child"
        assert en_child.get_path("en") == "/child"
        assert en_child.slug("en") == "child"
        assert en_child.get_path("nl") == "/child"
        assert en_child.slug("nl") == "child"
        assert en_child.get_path("fr") == "/child"
        assert en_child.slug("fr") == "child"

    def test_node_slug_language(self, client):
        """ A node with different slugs for different languages """
        translation.activate('en')
        root = Node.root()
        child = root.add("child")
        # import pytest; pytest.set_trace()
        child.rename("kind", language="nl")
        child.rename("enfant", language="fr")

        translation.activate('nl')
        nl_child = Node.get("/kind")
        assert nl_child == child
        assert nl_child.path == "/kind"
        assert nl_child.slug() == "kind"
        assert nl_child.get_path("nl") == "/kind"

        assert nl_child.get_path("en") == "/child"
        assert nl_child.slug("en") == "child"
        assert nl_child.get_path("fr") == "/enfant"
        assert nl_child.slug("fr") == "enfant"

    def test_node_slug_offspring_language(self, client):
        """ A node with different slugs for different languages,
            with children"""
        translation.activate('en')
        root = Node.root()
        child = root.add("child")
        child1 = child.add("grandchild1")
        child2 = child.add("grandchild2")

        # import pytest; pytest.set_trace()
        child.rename("kind", language="nl")
        child2.rename("kleinkind2", language="nl")


        translation.activate('nl')
        nl_child2 = Node.get("/kind/kleinkind2")
        assert nl_child2 == child2
        assert nl_child2.path == "/kind/kleinkind2"

        nl_child1 = Node.get("/kind/grandchild1")
        assert nl_child1 == child1
        assert nl_child1.path == "/kind/grandchild1"

    def test_rename_default(self, client):
        """ rename on a node with no explicit language specified,
            which should rename all nodes, if possible """
        translation.activate('en')
        root = Node.root()
        r1 = root.add("r1")

        r1.rename("rr1")

        assert r1.paths.count() == 3
        assert r1.path == "/rr1"
        translation.activate('nl')
        assert r1.path == "/rr1"
        translation.activate('fr')
        assert r1.path == "/rr1"
        ## ook weer recursief

    def test_node_child(self, client):
        """ test the node.child method """
        translation.activate('en')
        root = Node.root()
        child = root.add("child")

        assert root.child("child") == child

    def test_node_child_langswitch(self, client):
        """ test the node.child method """
        translation.activate('en')
        root = Node.root()
        child = root.add("child")

        translation.activate('fr')
        assert root.child("child") == child

    def test_children(self, client):
        """ find the children of a node """
        translation.activate('en')
        root = Node.root()
        r1 = root.add("r1")
        r2 = root.add("r2")
        r3 = root.add("r3")

        r2.rename("rr2", language="en")

        assert list(root.children()) == [r1, r2, r3]


class TestContent(object):
    pass

