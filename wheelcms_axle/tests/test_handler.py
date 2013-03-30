from wheelcms_axle.main import MainHandler
from wheelcms_axle.models import Node
from wheelcms_axle.tests.models import Type1, Type1Type

from two.ol.base import NotFound, Redirect, handler
import pytest

from twotest.util import create_request
from django.contrib.auth.models import User

class MainHandlerTestable(MainHandler):
    """ intercept template() call to avoid rendering """
    def render_template(self, template, **context):
        return dict(template=template, context=context)

    def template(self, path):
        return dict(path=path, context=self.context)

    def handle_reserved(self):
        """ should result in 'reserved' being a reserved kw """

    def foobar(self):
        """ should not result in a reserved keyworkd """

    @handler
    def decorated(self):
        pass


def superuser_request(path, method="GET", **data):
    superuser, _ = User.objects.get_or_create(username="superuser",
                                                   is_superuser=True)
    request = create_request(method, path, data=data)
    request.user = superuser
    return request

class TestMainHandler(object):
    def test_coerce_instance(self, client):
        """ coerce a dict holding an instance path """
        root = Node.root()
        a = root.add("a")
        res = MainHandler.coerce(dict(instance="a"))
        assert 'instance' in res
        assert res['instance'] == a
        assert 'parent' not in res

    def test_coerce_parent(self, client):
        """ coerce a dict holding an parent path """
        root = Node.root()
        a = root.add("a")
        res = MainHandler.coerce(dict(parent="a"))
        assert 'parent' in res
        assert res['parent'] == a
        assert 'instance' not in res

    def test_coerce_instance_parent(self, client):
        """ coerce a dict holding both instance and parent """
        root = Node.root()
        a = root.add("a")
        b = a.add("b")
        res = MainHandler.coerce(dict(instance="b", parent="a"))
        assert 'instance' in res
        assert 'parent' in res
        assert res['instance'] == b
        assert res['parent'] == a

    def test_coerce_instance_notfound(self, client):
        """ coerce a non-existing path for instance """
        pytest.raises(NotFound, MainHandler.coerce, dict(instance="a"))

    def test_coerce_parent_notfound(self, client):
        """ coerce a non-existing path for parent """
        pytest.raises(NotFound, MainHandler.coerce, dict(parent="a"))


    def test_create_get_root(self, client):
        """ test create on root - get """
        root = Node.root()
        Type1(node=root).save()
        request = superuser_request("/", type=Type1.get_name())
        handler = MainHandlerTestable(request=request, instance=root)
        create = handler.create()
        assert create['path'] == "wheelcms_axle/create.html"
        assert 'form' in create['context']

    def test_update_root(self, client):
        """ test /edit """
        root = Node.root()
        Type1(node=root).save()
        request = superuser_request("/edit", method="POST", type=Type1.get_name())
        instance = MainHandlerTestable.coerce(dict(instance=""))
        handler = MainHandlerTestable(request=request, instance=instance)
        update = handler.update()
        assert update['path'] == "wheelcms_axle/update.html"
        assert 'form' in update['context']

    def test_create_attach_get(self, client):
        """ get the form for attaching content """
        root = Node.root()
        Type1(node=root).save()
        request = superuser_request("/", type=Type1.get_name())
        handler = MainHandlerTestable(request=request, instance=root)
        create = handler.create(type=Type1.get_name(), attach=True)
        assert create['path'] == "wheelcms_axle/create.html"
        assert 'form' in create['context']

    def test_create_attach_post(self, client):
        """ post the form for attaching content """
        request = superuser_request("/create", method="POST",
                                      title="Test")
        root = Node.root()
        handler = MainHandler(request=request, post=True,
                              instance=dict(instance=root))
        pytest.raises(Redirect, handler.create, type=Type1.get_name(), attach=True)

        root = Node.root()
        assert root.contentbase.title == "Test"

    def test_attached_form(self, client):
        """ The form when attaching should not contain a slug field since it
            will be attached to an existing node """
        root = Node.root()
        Type1(node=root).save()
        request = superuser_request("/")
        handler = MainHandlerTestable(request=request, instance=root)
        create = handler.create(type=Type1.get_name(), attach=True)

        form = create['context']['form']
        assert 'slug' not in form.fields

    def test_create_post(self, client):
        request = superuser_request("/create", method="POST",
                                      title="Test",
                                      slug="test")
        root = Node.root()
        handler = MainHandler(request=request, post=True,
                              instance=dict(instance=root))
        pytest.raises(Redirect, handler.create, type=Type1.get_name())

        node = Node.get("/test")
        assert node.contentbase.title == "Test"

    def test_update_post(self, client):
        root = Node.root()
        Type1(node=root, title="Hello").save()
        request = superuser_request("/edit", method="POST",
                                      title="Test",
                                      slug="")
        root = Node.root()
        handler = MainHandler(request=request, post=True, instance=root)
        pytest.raises(Redirect, handler.update)

        root = Node.root()
        assert root.contentbase.title == "Test"

    def test_reserved_default(self, client):
        reserved = MainHandlerTestable.reserved()
        assert 'create' in reserved
        assert 'list' in reserved
        assert 'update' in reserved

    def test_reserved_handle_explicit(self, client):
        reserved = MainHandlerTestable.reserved()
        assert 'reserved' in reserved
        assert 'foobar' not in reserved

    def test_reserved_decorator(self, client):
        reserved = MainHandlerTestable.reserved()
        assert 'decorated' in reserved


class TestBreadcrumb(object):
    """ test breadcrumb generation by handler """

    def test_unattached_root(self, client):
        root = Node.root()
        request = create_request("GET", "/edit")
        handler = MainHandlerTestable(request=request, instance=root)
        assert handler.breadcrumb() == [("Unattached rootnode", '')]

    def test_attached_root(self, client):
        """ A root node with content attached. Its name should not be
            its title but 'Home' """
        root = Node.root()
        Type1(node=root, title="The rootnode of this site").save()
        request = create_request("GET", "/")
        handler = MainHandlerTestable(request=request, instance=root)
        assert handler.breadcrumb() == [("Home", '')]

    def test_sub(self, client):
        """ a child with content under the root """
        root = Node.root()
        Type1(node=root, title="Root").save()
        child = root.add("child")
        Type1(node=child, title="Child").save()
        request = create_request("GET", "/")

        handler = MainHandlerTestable(request=request, instance=child)
        assert handler.breadcrumb() == [("Home", '/'), ("Child", "")]

        ## root should ignore child
        handler = MainHandlerTestable(request=request, instance=root)
        assert handler.breadcrumb() == [("Home", '')]

    def test_subsub(self, client):
        """ a child with content under the root """
        root = Node.root()
        Type1(node=root, title="Root").save()
        child = root.add("child")
        Type1(node=child, title="Child").save()
        child2 = child.add("child2")
        Type1(node=child2, title="Child2").save()
        request = create_request("GET", "/")

        handler = MainHandlerTestable(request=request, instance=child2)
        assert handler.breadcrumb() == [("Home", '/'), ("Child", "/child"),
                                        ("Child2", "")]

        ## root should ignore child
        handler = MainHandlerTestable(request=request, instance=root)
        assert handler.breadcrumb() == [("Home", '')]

    def test_subsub_unattached(self, client):
        """ a child with content under the root, lowest child unattached """
        root = Node.root()
        Type1(node=root, title="Root").save()
        child = root.add("child")
        Type1(node=child, title="Child").save()
        child2 = child.add("child2")
        request = create_request("GET", "/")

        handler = MainHandlerTestable(request=request, instance=child2)
        assert handler.breadcrumb() == [("Home", '/'), ("Child", "/child"),
                                        ("Unattached node /child/child2", "")]

    def test_parent_instance(self, client):
        """ handler initialized with a parent but no instance. Should
            mean edit mode, but for now assume custom breadcrumb context """
        root = Node.root()
        Type1(node=root, title="Root").save()
        request = create_request("GET", "/")
        handler = MainHandlerTestable(request=request, kw=dict(parent=root))

        assert handler.breadcrumb() == []


    def test_subsub_operation(self, client):
        """ a child with content under the root """
        root = Node.root()
        Type1(node=root, title="Root").save()
        child = root.add("child")
        Type1(node=child, title="Child").save()
        child2 = child.add("child2")
        Type1(node=child2, title="Child2").save()
        request = create_request("GET", "/")

        handler = MainHandlerTestable(request=request, instance=child2)
        assert handler.breadcrumb(operation="Edit") == [
            ("Home", '/'), ("Child", "/child"),
            ("Child2", "/child/child2"), ("Edit", "")]

    def test_create_get(self, client):
        """ create should override and add Create operation crumb """
        root = Node.root()
        Type1(node=root, title="Root").save()
        child = root.add("child")
        Type1(node=child, title="Child").save()
        request = superuser_request("/child/create")

        handler = MainHandlerTestable(request=request, instance=child)
        context = handler.create(type=Type1.get_name())['context']
        assert 'breadcrumb' in context
        assert context['breadcrumb'] == [('Home', '/'), ('Child', '/child'),
                                         ('Create "%s"' % Type1Type.title, '')]

    def test_update(self, client):
        """ update should override and add Update operation crumb """
        root = Node.root()
        Type1(node=root, title="Root").save()
        child = root.add("child")
        Type1(node=child, title="Child").save()
        request = superuser_request("/child/create")

        handler = MainHandlerTestable(request=request, instance=child)
        context = handler.update()['context']
        assert 'breadcrumb' in context
        assert context['breadcrumb'] == [
                   ('Home', '/'), ('Child', '/child'),
                   ('Edit "%s" (%s)' % (child.content().title,
                                        Type1Type.title), '')]

class TestAction(object):
    def test_action_root(self, client):
        root = Node.root()
        Type1(node=root, title="Root").save()
        #child = root.add("child")
        #Type1(node=child, title="Child").save()
        request = superuser_request("/+hello")
        handler = MainHandlerTestable(request=request, instance=root,
                                      kw=dict(action="hello"))
        result = handler.view()
        assert len(result) == 5
        result, request, handler, spoke, action = result
        assert result == "Hello"
        assert request
        assert handler
        assert action == "hello"
        assert spoke.instance == root.content()

    def test_action_child(self, client):
        root = Node.root()
        Type1(node=root, title="Root").save()
        child = root.add("child")
        Type1(node=child, title="Child").save()
        request = superuser_request("/child/+hello")
        handler = MainHandlerTestable(request=request, instance=child,
                                      kw=dict(action="hello"))
        result = handler.view()
        assert len(result) == 5
        result, request, handler, spoke, action = result
        assert result == "Hello"
        assert request
        assert handler
        assert action == "hello"
        assert spoke.instance == child.content()




