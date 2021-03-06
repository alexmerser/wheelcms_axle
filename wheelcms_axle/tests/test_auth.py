"""
    Test auth/role/permission related stuff

"""
from mock import patch, PropertyMock, MagicMock
import pytest
from twotest.util import create_request

from django.contrib.auth.models import User, Group

from drole.models import RolePermission

from wheelcms_axle import permissions as p, roles
from wheelcms_axle import models

from .models import Type1Type
from ..auth import has_access, Permission, Role, assign_perms, update_perms
from ..auth import get_roles_in_context, assign

from .fixtures import superuser

def permpatch(return_value):
    """ patch the default roles returned by Type1Type.permission_assignment """
    return patch("wheelcms_axle.tests.models.Type1Type.permission_assignment",
                 new_callable=PropertyMock(return_value=return_value))

@pytest.fixture
def testpermission():
    return Permission('testpermission')

@pytest.fixture
def testrole():
    return Role('testrole')


@pytest.fixture
def anon_request():
    return create_request("GET", "/")

@pytest.fixture
def user(username="testuser", **kw):
    return User.objects.get_or_create(username=username, **kw)[0]

@pytest.fixture
def auth_request():
    r = create_request("GET", "/")
    r.user = user()
    return r

@pytest.fixture
def super_request():
    r = create_request("GET", "/")
    r.user = superuser()
    return r

from wheelcms_axle.workflows.default import Workflow

@pytest.mark.usefixtures("localtyperegistry")
class TestAssignments(object):
    type = Type1Type

    def setup(self):
        ## Make sure there are no workflow permission updates
        self.wfpatch = patch("wheelcms_axle.tests.models.Type1Type.workflow",
                             return_value=Workflow)
        self.wfpatch.start()

    def teardown(self):
        self.wfpatch.stop()

    @permpatch({})
    def test_assignment_blank(self, pp, client):
        t = Type1Type.create()
        t.save()

        # import pytest; pytest.set_trace()
        assert not RolePermission.assignments(t.instance).exists()

    @permpatch({p.view_content:(roles.owner,)})
    def test_assignment(self, pp, client):
        t = Type1Type.create()
        t.save()

        assert RolePermission.assignments(t.instance).count() == 1

    @permpatch({})
    def test_assign_perms_explicit(self, pp, client):
        t = Type1Type.create()
        t.save()

        assign_perms(t.instance, {p.view_content: (roles.owner,)})

        assert RolePermission.assignments(t.instance).exists()
        a = RolePermission.assignments(t.instance).all()[0]

        assert a.role == roles.owner
        assert a.permission == p.view_content

    @permpatch({})
    def test_assign_perms_twice(self, pp, client):
        t = Type1Type.create()
        t.save()

        assign_perms(t.instance, {Permission("p1"): (Role("r1"),)})
        assign_perms(t.instance, {Permission("p2"): (Role("r2"),)})

        assert RolePermission.assignments(t.instance).count() == 2
        a = RolePermission.assignments(t.instance).all()

        assert set((x.role for x in a)) == set((Role("r1"), Role("r2")))
        assert set((x.permission for x in a)) == \
               set((Permission("p1"), Permission("p2")))

    @permpatch({})
    def test_assign_perms_duplicate(self, pp, client):
        t = Type1Type.create()
        t.save()

        assign_perms(t.instance, {Permission("p"): (Role("r"),)})
        assign_perms(t.instance, {Permission("p"): (Role("r"),)})

        assert RolePermission.assignments(t.instance).count() == 1
        a = RolePermission.assignments(t.instance).all()[0]
        assert a.role == Role("r")
        assert a.permission == Permission("p")

    @permpatch({})
    def test_update_perms(self, pp, client):
        t = Type1Type.create()
        t.save()

        assign_perms(t.instance, {Permission("p"): (Role("r"),)})
        update_perms(t.instance, {Permission("p"): (Role("r1"),)})

        assert RolePermission.assignments(t.instance).count() == 1
        a = RolePermission.assignments(t.instance).all()[0]
        assert a.role == Role("r1")
        assert a.permission == Permission("p")

    @permpatch({})
    def test_update_perms_add(self, pp, client):
        t = Type1Type.create()
        t.save()

        assign_perms(t.instance, {Permission("p"): (Role("r"),)})
        update_perms(t.instance, {Permission("p1"): (Role("r1"),)})

        rp = RolePermission.assignments(t.instance)
        assert rp.count() == 2

        assert set((i.permission, i.role) for i in rp) == \
               set(((Permission("p"), Role("r")),
                    (Permission("p1"), Role("r1"))))



class TestHasAccess(object):
    @permpatch({testpermission():(testrole(),)})
    @patch('wheelcms_axle.auth.get_roles_in_context',
                       return_value=set((testrole(),)))
    def test_has_access_class(self, gric, pp, auth_request, testpermission):
        assert has_access(auth_request, Type1Type, None, testpermission)

    @patch('wheelcms_axle.auth.get_roles_in_context',
                       return_value=set((testrole(),)))
    def test_has_access_defaultclass(self, gric, auth_request, testpermission):
        with patch("wheelcms_axle.spoke.Spoke.permission_assignment",
                   new_callable=PropertyMock(
                   return_value={testpermission:(testrole(),)})):
            assert has_access(auth_request, None, None, testpermission)

    @permpatch({testpermission():(testrole(),)})
    @patch('wheelcms_axle.auth.get_roles_in_context',
                       return_value=set((testrole(),)))
    def test_not_active_no_access(self, gric, pp, auth_request, testpermission):
        auth_request.user.is_active = False
        auth_request.user
        assert not has_access(auth_request, Type1Type, None, testpermission)

    @permpatch({testpermission():(testrole(),)})
    @patch('wheelcms_axle.auth.get_roles_in_context',
                       return_value=set())
    def test_no_access_class(self, gric, pp, auth_request, testpermission):
        assert not has_access(auth_request, Type1Type, None, testpermission)

    @permpatch({testpermission():(testrole(),)})
    @patch('wheelcms_axle.auth.get_roles_in_context',
                       return_value=set((testrole(),)))
    def test_has_access_instance(self, gric, pp, auth_request, testpermission):
        t = Type1Type.create().save()
        assert has_access(auth_request, Type1Type, t, testpermission)

    @permpatch({testpermission():(testrole(),)})
    @patch('wheelcms_axle.auth.get_roles_in_context',
                       return_value=set())
    def test_no_access_instance(self, gric, pp, auth_request, testpermission):
        t = Type1Type.create().save()
        assert not has_access(auth_request, Type1Type, t, testpermission)

    @permpatch({testpermission():(testrole(),)})
    def test_superuser_always(self, client, super_request):
        """ The superuser always has access """
        t = Type1Type.create().save()
        assert has_access(super_request, Type1Type, t, testpermission)

    def test_has_access_public(self, anon_request):
        assert has_access(anon_request, None, None, p.public)

@pytest.mark.usefixtures("localtyperegistry")
class TestRolesContext(object):
    """ Verify a user gets the correct roles assigned, locally / globally """
    type = Type1Type

    def test_anon_has_anonymous(self, anon_request):
        """ Every user, even anonymous, has the anonymous role """
        assert roles.anonymous in get_roles_in_context(anon_request, Type1Type)

    def test_auth_has_anonymous(self, auth_request):
        """ Every user, even anonymous, has the anonymous role """
        assert roles.anonymous in get_roles_in_context(auth_request, Type1Type)

    def test_auth_has_member(self, auth_request):
        """ Every authenticated user has the "member" role """
        assert roles.member in get_roles_in_context(auth_request, Type1Type)

    def test_assigned_role_user(self, client, auth_request):
        """ Test for an explicitly assigned role """
        models.Role.objects.get_or_create(user=auth_request.user,
                                          role=Role("special.role"))
        assert Role("special.role") in \
               get_roles_in_context(auth_request, Type1Type)

    def test_assigned_role_group(self, client, auth_request):
        """ Test for an explicitly assigned role """
        group = Group.objects.get_or_create(name="testgroup")[0]
        group.user_set.add(auth_request.user)
        models.Role.objects.get_or_create(group=group,
                                          role=Role("special.grouprole"))
        assert Role("special.grouprole") in \
               get_roles_in_context(auth_request, Type1Type)

    def test_owner_role(self, client, auth_request):
        """ the owner of an object gets the owner role """
        t = Type1Type.create(owner=auth_request.user).save()

        assert roles.owner in get_roles_in_context(auth_request, Type1Type, t)

    def test_owner_role_false(self, client, auth_request):
        """ only the owner of an object gets the owner role """
        t = Type1Type.create(owner=User.objects.get_or_create(
                                     username="other")[0]).save()

        assert not roles.owner in get_roles_in_context(auth_request, Type1Type,
                                                       t)

    ## superuser -- all roles, or always access?

class TestAssignDecorator(object):
    """ Test the auth.assign class decorator """
    def test_base(self):
        """ assign roles/perms on a class directly """
        @assign({'a':1})
        class T(object):
            pass

        assert hasattr(T, 'permission_assignment')
        assert T.permission_assignment['a'] == 1


    def test_traditional_decorated_child(self):
        """ Directly assign permission_assignment on parent, extend
            through decorator on child """
        class T(object):
            permission_assignment = {'a':1, 'b':2}
        @assign({'a':2, 'c':3})
        class Tchild(T):
            pass

        assert hasattr(Tchild, 'permission_assignment')
        assert T.permission_assignment == {'a':1, 'b':2}
        assert Tchild.permission_assignment == {'a':2, 'b':2, 'c': 3}

    def test_child_decorated(self):
        """ Both base and child class use decorator """
        @assign({'a':1, 'b':2})
        class T(object):
            pass
        @assign({'a':2, 'c':3})
        class Tchild(T):
            pass

        assert hasattr(Tchild, 'permission_assignment')
        assert T.permission_assignment == {'a':1, 'b':2}
        assert Tchild.permission_assignment == {'a':2, 'b':2, 'c': 3}


