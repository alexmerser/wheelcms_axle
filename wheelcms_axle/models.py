import mimetypes
import re
import os
import datetime

from django.db import models, IntegrityError
from django.utils import timezone
from django.contrib.auth.models import User

from userena.models import UserenaLanguageBaseProfile

from .impexp import WheelSerializer
## import pytz

from django.utils.translation import ugettext as _

class WheelProfile(UserenaLanguageBaseProfile):
    """ timezone, ... ?
    """
    ##timezone = models.CharField(max_length=100, default=config.DEFAULT_TIMEZONE,
    ##    choices=[(x, x) for x in pytz.common_timezones])
    inform = models.BooleanField(default=False)
    user = models.OneToOneField(User,
                                unique=True,
                                verbose_name=_('user'),
                                related_name='my_profile')

class NodeException(Exception):
    """ Base class for all Node exceptions """

class DuplicatePathException(NodeException):
    """ the path is already in use """

class InvalidPathException(NodeException):
    """ The path contains non-valid chars or is too short """

class NodeInUse(NodeException):
    """ the node already has content attached to it """

class CantRenameRoot(NodeException):
    """ the root's path is "" which cannot be changed """

class NodeBase(models.Model):
    ROOT_PATH = ""
    ALLOWED_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789_-"
    MAX_PATHLEN = 40
    POSITION_INTERVAL = 100

    validpathre = re.compile("^[%s]{1,%d}$" % (ALLOWED_CHARS, MAX_PATHLEN))

    path = models.CharField(max_length=MAX_PATHLEN, blank=False, unique=True)
    position = models.IntegerField(default=0)


    class Meta:
        abstract = True

    def content(self):
        try:
            return self.contentbase.content()
        except Content.DoesNotExist:
            return None

    @classmethod
    def get(cls, path):
        """ retrieve node directly by path. Returns None if not found """
        try:
            return cls.objects.get(path=path)
        except cls.DoesNotExist:
            if path == "":
                return cls.root()

            return None

    def set(self, content, replace=False):
        """
            Set content on the node, optionally replacing existing
            content. This is a more friendly way of setting the node
            on a Content directly
        """
        ## just to be sure, in case it's of type Content in stead of
        ## subclass
        content = content.content()

        old = None
        try:
            if self.contentbase:
                if replace:
                    old = self.content()
                    old.node = None
                    old.save()
                else:
                    raise NodeInUse()
        except Content.DoesNotExist:
            pass

        self.contentbase = content #.content_ptr  # XXX is _ptr documented?
        #content.node = self
        content.save()
        self.save()

        return old

    @classmethod
    def root(cls):
        return cls.objects.get_or_create(path=cls.ROOT_PATH)[0]

    def isroot(self):
        return self.path == self.ROOT_PATH

    def add(self, path, position=-1, after=None, before=None):
        """ handle invalid paths (invalid characters, empty, too long) """
        ## lowercasing is the only normalization we do
        path = path.lower()

        if not self.validpathre.match(path):
            raise InvalidPathException(path)

        children = self.children()
        positions = (c.position for c in self.children())

        if after:
            try:
                afterafter_all = self.childrenq(position__gt=after.position,
                                            order="position")
                afterafter = afterafter_all.get()
                position = (after.position + afterafter.position) / 2
                if position == after.position:
                    ## there's a conflict. the new position will be 
                    ## "after.position + POSITION_INTERVAL", renumber
                    ## everything else
                    position = after.position + self.POSITION_INTERVAL
                    for i, n in enumerate(afterafter_all):
                        n.position = position + ((i + 1) * self.POSITION_INTERVAL)
                        n.save()
                    # XXX self.debug("repositioning children")
            except Node.DoesNotExist:
                ## after is the last childnode
                position = after.position + self.POSITION_INTERVAL
        elif before:
            try:
                beforebefore_all = self.childrenq(position__lt=before.position,
                                            order="position")
                beforebefore = beforebefore_all.latest("position")
                position = (before.position + beforebefore.position) / 2
                if position == beforebefore.position:
                    ## there's a conflict. the new position will be 
                    ## "before.position", renumber before and everything
                    ## else after it.
                    position = before.position
                    everything_after = self.childrenq(
                                           position__gte=before.position,
                                           order="position")
                    for i, n in enumerate(everything_after):
                        n.position = position + ((i + 1) *
                                                 self.POSITION_INTERVAL)
                        n.save()
                    # XXX self.debug("repositioning children")
            except Node.DoesNotExist:
                ## before is the first childnode
                position = before.position - self.POSITION_INTERVAL
        elif position == -1:
            if children.count():
                position = max(positions) + self.POSITION_INTERVAL
            else:
                position = 0

        child = self.__class__(path=self.path + "/" + path,
                               position=position)
        try:
            child.save()
            # XXX child.info(action=create)
        except IntegrityError:
            raise DuplicatePathException(path)
        return child

    def parent(self):
        """ return the parent for this node """
        if self.isroot():
            return self
        parentpath, mypath = self.path.rsplit("/", 1)
        parent = self.__class__.objects.get(path=parentpath)
        return parent

    def childrenq(self, order="position", **kw):
        """ return the raw query for children """
        return self.__class__.objects.filter(
                  path__regex="^%s/[%s]+$" % (self.path, self.ALLOWED_CHARS),
                  **kw
                  ).order_by(order)

    def children(self, order="position"):
        return self.childrenq(order=order)

    def slug(self):
        """ last part of self.path """
        return self.path.rsplit("/", 1)[-1]

    def rename(self, slug):
        """ change the slug """
        if self.isroot():
            raise CantRenameRoot()

        newpath = self.path.rsplit("/", 1)[0] + "/" + slug
        if Node.objects.filter(path=newpath).count():
            raise DuplicatePathException(newpath)
        ## do something transactionish?
        for childs in Node.objects.filter(path__startswith=self.path + '/'):
            remainder = childs.path[len(self.path):]
            childs.path = newpath + remainder
            childs.save()
        self.path = newpath
        self.save()

    def __unicode__(self):
        """ readable representation """
        return u"path %s pos %d" % (self.path or '/', self.position)

WHEEL_NODE_BASECLASS = NodeBase
class Node(WHEEL_NODE_BASECLASS):
    pass

def far_future():
    """ default expiration is roughly 20 years from now """
    return timezone.now() + datetime.timedelta(days=(20*365+8))

class ContentClass(models.Model):
    name = models.CharField(max_length=256, blank=False)

class ContentBase(models.Model):
    CLASSES = ()

    serializer = WheelSerializer

    node = models.OneToOneField(Node, related_name="contentbase", null=True)
    title = models.CharField(max_length=256, blank=False)
    created = models.DateTimeField(blank=True, null=True)
    modified = models.DateTimeField(blank=True, null=True)
    publication = models.DateTimeField(blank=True, null=True,
                                       default=timezone.now)
    expire = models.DateTimeField(blank=True, null=True,
                                  default=far_future)

    ## workflow determines possible states and their meaning
    state = models.CharField(max_length=30, blank=True)

    template = models.CharField(max_length=255, blank=True)

    ## one could argue that this can be a property on a node
    navigation = models.BooleanField(default=False)

    meta_type = models.CharField(max_length=20)

    ## can be null for now, should move to null=False eventually
    owner = models.ForeignKey(User, null=True)

    ## class..
    classes = models.ManyToManyField(ContentClass, related_name="content")

    class Meta:
        abstract = True

    def save(self, *a, **b):
        ## XXX can this be replaced by a default on meta_type?
        mytype = self.__class__.__name__.lower()
        self.meta_type = mytype
        self.modified = timezone.now()
        if self.created is None:
            self.created = timezone.now()
        ## find associated spoke to find workflow default?
        ## if not self.state and state not in b, get default from spoke
        if not self.state and 'state' not in b:
            self.state = self.spoke().workflow().default

        super(ContentBase, self).save(*a, **b)
        for klass in self.CLASSES:
            self.classes.add(ContentClass.objects.get_or_create(name=klass)[0])
        return self  ## foo = x.save() is nice

    def content(self):
        if self.meta_type:
            return getattr(self, self.meta_type)

    def spoke(self):
        """ return the spoke for this model """
        return type_registry.get(self.meta_type)(self)

    @classmethod
    def get_name(cls):
        ## include app_label ? #486
        return cls._meta.object_name.lower()

    def __unicode__(self):
        try:
            return u"%s connected to node %s: %s" % \
                    (self.meta_type, self.node, self.title)
        except Node.DoesNotExist:
            return u"Unconnected %s: %s" % (self.meta_type, self.title)

WHEEL_CONTENT_BASECLASS = ContentBase

class Content(WHEEL_CONTENT_BASECLASS):
    pass


class ClassContentManager(models.Manager):
    def __init__(self, name):
        self.name = name

    def get_query_set(self):
        return ContentClass.objects.get_or_create(name=self.name)[0].content.all()

class FileContent(Content):
    FILECLASS = "wheel.file"
    CLASSES = Content.CLASSES + (FILECLASS, )

    objects = models.Manager()
    instances = ClassContentManager(FILECLASS)

    content_type = models.CharField(blank=True, max_length=256)
    filename = models.CharField(blank=True, max_length=256)

    class Meta(Content.Meta):
        abstract = True


    def save(self, *a, **b):
        """
            Intercept save, fill in defaults for filename and mimetype if
            not explicitly set
        """
        if not self.filename:
            self.filename = self.storage.name or self.title
            ## guess extension if missing?
        self.filename = os.path.basename(self.filename)

        if not self.content_type:
            type, encoding = mimetypes.guess_type(self.filename)
            if type is None:
                type = "application/octet-stream"
            self.content_type = type
        return super(FileContent, self).save(*a, **b)


class ImageContent(FileContent):
    IMAGECLASS = "wheel.image"
    CLASSES = FileContent.CLASSES + ("wheel.image", )

    objects = models.Manager()
    instances = ClassContentManager(IMAGECLASS)

    class Meta(FileContent.Meta):
        abstract = True


class Configuration(models.Model):
    title = models.CharField(max_length=256, blank=False)
    description = models.TextField(blank=True)
    theme = models.CharField(max_length=256, blank=True, default="default")

    @classmethod
    def config(cls):
        """ singleton-ish pattern """
        try:
            instance = Configuration.objects.all()[0]
        except IndexError:
            instance = Configuration()
            instance.save()
        return instance


class TypeRegistry(dict):
    def register(self, t):
        self[t.name()] = t

from wheelcms_axle.registry import Registry

type_registry = Registry(TypeRegistry())
