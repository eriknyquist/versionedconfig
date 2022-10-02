import sys
import inspect

from versionedobj.exceptions import InvalidVersionAttributeError, InputValidationError
from versionedobj.utils import _ObjField, _iter_obj_attrs, _walk_obj_attrs


def migration(cls, from_version, to_version):
    """
    Decorator for migration functions. Use this decorator on any function or method
    that should be used for migrating an object from one version to another.

    :param cls: Class object to add migration to
    :param from_version: Version to migrate from. If you are migrating an object that\
        previously had no version number, use 'None' here.
    :param to_version: Version to migrate to
    """
    def _inner_migration(migration_func):
        try:
            version = cls.__dict__['version']
        except KeyError:
            raise ValueError("Cannot add migration to un-versioned object. Add a 'version' attribute.")

        cls._vobj__migrations.append((from_version, to_version, migration_func))

    return _inner_migration


class MigrationResult(object):
    """
    Value returned by Serializer.from_dict, Serializer.from_file, and Serializer.from_json methods,
    if a successful or partial object migration was performed.

    :ivar old_version: the object version before migration was attempted
    :ivar target_version: the target version of the migration (current version)
    :ivar version_reached: the actual object version after migration (this should\
        match target_version after a successful migration)
    :ivar bool success: True if migration was successful, false otherwise
    """
    def __init__(self, old_version, target_version, version_reached, success):
        self.old_version = old_version
        self.target_version = target_version
        self.version_reached = version_reached
        self.success = success


class CustomValue(object):
    """
    Abstract class that can be sub-classed if you want to serialize/deserialize
    a custom class that the standard JSON parser is not handling the way you want
    """
    def to_dict(self):
        """
        Convert this object instance to something that is suitable for json.dump

        :return: object instance data as a dict, or a single value
        :rtype: any object
        """
        raise NotImplementedError()

    def from_dict(self, attrs):
        """
        Load this object instance with values from a dict returned by json.load

        :param dict attrs: object instance data
        """
        raise NotImplementedError()


class __Meta(type):
    """
    Metaclass for VersionedObject, creates the 'migrations' class attribute
    """
    def __new__(cls, name, bases, dic):
        dic['_vobj__migrations'] = []
        return super().__new__(cls, name, bases, dic)


class VersionedObject(metaclass=__Meta):
    """
    Versioned object class supporting saving/loading to/from JSON files, and
    migrating older files to the current version
    """

    def __init__(self, initial_values={}):
        """
        :param dict: map of initial values. Keys are the field name, and values are\
            the initial values to set.
        """
        self._vobj__populate_instance()

        # Set alternate initial values, if any
        if initial_values:
            for field in _walk_obj_attrs(self):
                dotname = field.dot_name()
                if dotname in initial_values:
                    field.value = initial_values[dotname]
                    field.set_obj_field(self)

    def _vobj__populate_instance(self):
        for n in _iter_obj_attrs(self.__class__):
            val = getattr(self.__class__, n)

            vobj_class = None
            if isinstance(val, VersionedObject):
                vobj_class = val.__class__
            elif inspect.isclass(val) and issubclass(val, VersionedObject):
                vobj_class = val

            if vobj_class:
                if hasattr(val, 'version'):
                    raise InvalidVersionAttributeError(f"{vobj_class.__name__} cannot have a version attribute. "
                                                        "Only the top-level object can have a version attribute.")

                val = vobj_class()

            setattr(self, n, val)

    @classmethod
    def _vobj__migrate(cls, version, attrs):
        old_version = attrs.get('version', None)
        version_before_migration = old_version
        version_after_migration = old_version

        result = None

        if old_version != version:
            result = MigrationResult(old_version, version, None, True)

            # Attempt migrations
            for fromversion, toversion, migrate in cls._vobj__migrations:
                if fromversion == version_after_migration:
                    attrs = migrate(attrs)

                version_after_migration = toversion
                if toversion == version:
                    break

            if version_after_migration != version:
                result.success = False

            result.version_reached = version_after_migration

        return result, attrs

    def __getitem__(self, key):
        field = _ObjField.from_dot_name(key, self)
        return field.get_obj_field(self)

    def __setitem__(self, key, value):
        field = _ObjField.from_dot_name(key, self)
        field.value = value
        field.set_obj_field(self)

    def __iter__(self):
        for field in _walk_obj_attrs(self):
            yield (field.dot_name(), field.get_obj_field(self))

_ObjField.set_obj_class(VersionedObject)


