import re

from django.utils import translation
from django.db import models, IntegrityError
from django.conf import settings
from django.core.urlresolvers import reverse


class NodeException(Exception):
    """ Base class for all Node exceptions """

class DuplicatePathException(NodeException):
    """ the path is already in use """

class InvalidPathException(NodeException):
    """ The path contains non-valid chars or is too short """

class NodeInUse(NodeException):
    """ the node already has content attached to it """

class CantMoveToOffspring(NodeException):
    """ a node cannot be moved to one of its offspring nodes """

class CantRenameRoot(NodeException):
    """ the root's path is "" which cannot be changed """

class NodeNotFound(NodeException):
    """ raised if a node is not found """

from django.db.models.query import QuerySet
from django.utils import timezone
from django.db.models import Q

def get_language():
    language = translation.get_language()
    if language not in getattr(settings, 'CONTENT_LANGUAGES', ()) and getattr(settings, 'FALLBACK', None):
        language = settings.FALLBACK
    return language

class NodeQuerySet(QuerySet):
    def children(self, node, language=None):
        """ only return direct children """
        language = language or get_language()
        return self.filter(
                  paths__path__regex="^%s/[%s]+$" %
                      (node.path, Node.ALLOWED_CHARS),
                  paths__language=language
                  )

    def offspring(self, node, language=None):
        """ children, grandchildren, etc """
        language = language or get_language()
        return self.filter(
                  paths__path__regex="^%s/[%s]+" % (node.path, Node.ALLOWED_CHARS), paths__language=language
                  )

    def attached(self):
        return self.filter(contentbase__isnull=False)

    def public(self):
        now = timezone.now()
        return (self.attached().filter(
                Q(contentbase__publication__isnull=True)|
                Q(contentbase__publication__lte=now),
                Q(contentbase__expire__isnull=True)|
                Q(contentbase__expire__gte=now),
                contentbase__state='published'))


class NodeManager(models.Manager):
    def get_query_set(self):
        """ Return the NodeQuerySet that supports additional filters """
        return NodeQuerySet(self.model)

    def attached(self):
        return self.all().attached()

    def public(self):
        return self.all().public()

    def children(self, node):
        return self.all().children(node)

    def offspring(self, node, language=None):
        return self.all().offspring(node, language)

    def visible(self, user):
        """
            XXX TODO: when is content visible? May be even more
            complex when roles are supported
        """


class NodeBase(models.Model):
    ROOT_PATH = ""
    ALLOWED_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789_-"
    MAX_PATHLEN = 100
    POSITION_INTERVAL = 100

    validpathre = re.compile("^[%s]{1,%d}$" % (ALLOWED_CHARS, MAX_PATHLEN))

    # path = models.CharField(max_length=255, blank=False, unique=True)
    position = models.IntegerField(default=0)

    objects = NodeManager()

    class Meta:
        abstract = True

    def __init__(self, *args, **kw):
        self._slug = kw.get('slug', None)
        self._parent = kw.get('parent', None)
        try:
            del kw['slug']
        except KeyError:
            pass
        try:
            del kw['parent']
        except KeyError:
            pass

        super(NodeBase, self).__init__(*args, **kw)

    def content(self):
        from .content import Content
        try:
            return self.contentbase.content()
        except Content.DoesNotExist:
            return None

    @classmethod
    def get_nodepath(self, path, language=None):
        language = language or get_language()
        try:
            np = NodePath.objects.get(path=path, language=language)
            return np.node
        except NodePath.DoesNotExist:
            return None

    def get_path(self, language=None):
        return NodePath.get_for_node(self, language).path

    @property
    def path(self):
        return self.get_path()

    @classmethod
    def get(cls, path, language=None):
        """ retrieve node directly by path. Returns None if not found """
        node = cls.get_nodepath(path, language)
        if node:
            return node
        elif path == cls.ROOT_PATH:
            return cls.root()
        return None

    def set(self, content, replace=False): ## language
        """
            Set content on the node, optionally replacing existing
            content. This is a more friendly way of setting the node
            on a Content directly
        """
        ## just to be sure, in case it's of type Content in stead of
        ## subclass
        from .content import Content
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
        ## avoid updating last_modified
        content.save(update_lm=False)
        self.save()

        return old

    def save(self, *args, **kw):
        super(NodeBase, self).save(*args, **kw)
        """
            Create path entries for all supported languages
        """
        if self._slug is None:
            return

        for l in settings.CONTENT_LANGUAGES:
            if not self._parent:
                ## must be root, could just as well assign ''
                childpath = self._slug
            else:
                parentpath = self._parent.get_path(language=l)
                childpath = parentpath + '/' + self._slug
            NodePath.objects.get_or_create(node=self,
                                           path=childpath,
                                           language=l)
    @classmethod
    def root(cls):
        root_np = cls.get_nodepath(cls.ROOT_PATH)
        if root_np:
            return root_np

        # create the rootnode (no matter if the language is supported)
        # return it
        root = Node(slug='')
        root.save()
        #root.save()
        # root.create_paths()
        # try again, may return None if language not supported
        root_np = cls.get_nodepath(cls.ROOT_PATH)
        return root_np  # may be None

    def isroot(self):
        return self.path == self.ROOT_PATH

    def is_ancestor(self, node):
        return node.path.startswith(self.path + '/')

    def find_position(self, position=-1, after=None, before=None):
        children = self.children()
        positions = (c.position for c in self.children())

        if after:
            try:
                afterafter_all = self.childrenq(position__gt=after.position,
                                            order="position")[:1]
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
        return position

    def add(self, path, position=-1, after=None, before=None):
        """ handle invalid paths (invalid characters, empty, too long) """
        ## lowercasing is the only normalization we do
        path = path.lower()

        if not self.validpathre.match(path):
            raise InvalidPathException(path)

        position = self.find_position(position, after, before)


        child = self.__class__(slug=path, parent=self,
                               position=position)
        ##
        ## Verify the childpath is unique for each language-specific
        ## parent path. We could do something distinct() here perhaps
        ## in case languages share the same pathname
        for l in settings.CONTENT_LANGUAGES:
            p = self.paths.get(language=l).path + '/' + path
            if NodePath.objects.filter(path=p).exists():
                raise DuplicatePathException(path)
                
        try:
            child.save()
        except IntegrityError:
            raise DuplicatePathException(path)
        return child

    def move(self, child, position=-1, after=None, before=None):
        """ move (reorder) an existing child. This does not take into account
            that the child already has a position in the child-order, but that
            shouldn't make a significant difference

            This method does not move nodes to *different* nodes (e.g. paste)
       """

        position = self.find_position(position, after, before)
        child.position = position
        child.save()

    def paste(self, node, copy=False):
        """
            Move a node elsewhere in the tree, optionally copying the node
            (copy-paste) or deleting the original (cut-paste)
        """
        ## a move is just rewriting/renaming the child and its offspring,
        ## a copy is recreating the node

        ## ancestor nodes cannot be moved into offspring nodes, they can be
        ## copied, but avoid recursion.

        ## how to deal with the position? Insert at the bottom?

        from .content import ContentCopyException

        failed = []
        success = []

        def unique_slug(slug, language):
            mypath = self.get_path(language)
            orig_slug = slug
            count = 0
            while NodePath.objects.filter(path=mypath + '/' + slug, language=language).exists():
                slug = "%s_%d" % (orig_slug, count)
                count += 1
            return slug

        if copy:
            """
                Maak een node 'new' met basis nieuw pad
                genereer vertaling voor iedere taal met unieke slug
                kopieer content. Bij error, ruim op

                Voor alle directe children 'o':

                r, s, f = new.paste(o, copy=True)
                update s/f

                return new, s, f
            """
            origpath = node.path
            if origpath != '':
                origbase, slug = origpath.rsplit("/", 1)
            else:
                origbase, slug = "", "root"

            slug = unique_slug(slug)
            base = self.add(slug)
            if node.content():
                try:
                    node.content().copy(node=base)
                    success.append(node.path)
                except ContentCopyException:
                    failed.append((node.path, "Content cannot be copied"))
                    base.delete()
                    ## no need to continue
                    return base, success, failed

            """
                Een node kan meerdere paden hebben, en een node kan meerdere content objecten hebben,
                alles per taal. Dit is niet perse 1-1 gerelateerd, maar in de praktijk wel

                kopieren van een node betekent dus 
            """
            for o in Node.objects.offspring(node).order_by("path"):
                ## skip all offspring of a failed node
                for f, reason in failed:
                    if o.path.startswith(f + '/'):
                        break
                else:
                    path = self.path + '/' + slug + o.path[len(origpath):]
                    n, _ = Node.objects.get_or_create(path=path)
                    if o.content():
                        try:
                            o.content().copy(node=n)
                            success.append(o.path)
                        except ContentCopyException:
                            n.delete()
                            failed.append((o.path, "Content cannot be copied"))
            return base, success, failed

        else:
            if node == self or node.is_ancestor(self):
                raise CantMoveToOffspring()

            for language in settings.CONTENT_LANGUAGES:
                np = NodePath.get_for_node(node, language=language)
                nodepath = np.path

                oldbase, slug = nodepath.rsplit("/", 1)
                mypath = self.get_path(language)
                if oldbase == mypath:
                    ## pasting into its own parent, nothing to do
                    return node, success, failed

                slug = unique_slug(slug, language)

                ## XXX somehow batch/transaction this
                for childpath in NodePath.objects.filter(path__startswith=nodepath + '/',
                        language=language):
                    childpath.path = mypath + '/' + slug + childpath.path[len(nodepath):]
                    childpath.save()
                    success.append(childpath.path) # XXX dat is het nieuwe pad nu!

                np.path = mypath + '/' + slug
                np.save()

                ## move to end
                node.position = self.find_position(position=-1)
                node._slug = None
                node.save()
                success.append(node.path)

            return node, success, failed

    def remove(self, childslug):
        """ remove a child, recursively """
        child = self.child(childslug)
        if child is None:
            raise NodeNotFound(self.path + '/' + childslug)
        #recursive = Node.objects.filter(path__startswith=self.path + '/' +
        #                                                 childslug + '/')
        recursive = self.__class__.objects.offspring(child)
        recursive.delete()
        child.delete()

    def parent(self):
        """ return the parent for this node """
        if self.isroot():
            return self
        parentpath, mypath = self.path.rsplit("/", 1)
        parent = self.__class__.get(path=parentpath)
        return parent

    def childrenq(self, order="position", **kw):
        """ return the raw query for children """
        return self.__class__.objects.children(self).order_by(order).filter(**kw)

    def children(self, order="position"):
        return self.childrenq(order=order)

    def child(self, slug):
        """ return a specific child by its slug """
        childpath = self.path + '/' + slug

        return self.get(childpath)

    def slug(self, language=None):
        """ last part of self.path """
        return self.get_path(language).rsplit("/", 1)[-1]

    def rename(self, slug, language=None):
        """ change the slug """
        if self.isroot():
            raise CantRenameRoot()

        if language is None:
            languages = settings.CONTENT_LANGUAGES
        else:
            languages = [language]

        for language in languages:
            np = NodePath.get_for_node(self, language=language)
            path = np.path

            newpath = path.rsplit("/", 1)[0] + "/" + slug
            if NodePath.objects.filter(path=newpath, language=language).count():
                raise DuplicatePathException(newpath)

            ## do something transactionish?
            ## .offspring won't work here -- returns Nodes
            for childpath in NodePath.objects.filter(path__startswith=path + '/', language=language):
                remainder = childpath.path[len(path):]
                childpath.path = newpath + remainder
                childpath.save()

            np.path = newpath
            np.save()
        ## Must be cleared since not all languages are equal
        ## else self.save() will create new path entries based on the
        ## changed self._path, or restore the original path
        self._slug = None

        self.save()

    def get_absolute_url(self):
        ## strip any leading / since django will add that as well
        return reverse('wheel_main', kwargs={'instance':self.path.lstrip('/')})

    def __unicode__(self):
        """ readable representation """
        try:
            return u"path %s pos %d" % (self.path or '/', self.position)
        except Exception: # yuck, XXX
            return u"Unsaved node %s pos %d" % (self._slug or '/', self.position)

WHEEL_NODE_BASECLASS = NodeBase
class Node(WHEEL_NODE_BASECLASS):
    pass


class NodePath(models.Model):
    class Meta:
        unique_together = ('path', 'language')

    path = models.CharField(max_length=1024, blank=False)
    language = models.CharField(max_length=20, blank=False)
    
    node = models.ForeignKey(Node, blank=False, related_name="paths")

    def __unicode__(self):
        return "%s (%s)" % (self.path, self.language)

    @classmethod
    def get_for_node(cls, node, language=None):
        language = language or get_language()
        return node.paths.filter(language=language)[0]
