from datetime import datetime
import uuid

import couchdb
import couchdb.design
from couchdb.mapping import Document, Mapping
from couchdb.mapping import TextField, IntegerField, DateField, DictField
from couchdb.mapping import ListField, DateTimeField, BooleanField, ViewField


class Metadata(object):
    SERVER = None
    DB = None

def init_model(config):
    Metadata.SERVER = couchdb.Server(config['COUCHDB_HOST'])
    Metadata.DB = setup_db(config['COUCHDB_DATABASE'])

def setup_db(dbname):
    if dbname in Metadata.SERVER:
        db = Metadata.SERVER[dbname] 
        setup_views(db)
        return db
    else:
        db = Metadata.SERVER.create(dbname)
        setup_views(db)
        return db

def rebuild_db(dbname):
    if dbname in Metadata.SERVER:
        del Metadata.SERVER[dbname]
    return setup_db(dbname)


class DomainObject(Document):
    def save(self):
        self.store(Metadata.DB)

    @classmethod
    def get(cls, id):
        return cls.load(Metadata.DB, id)

    def delete(self):
        Metadata.DB.delete(self)

    def to_dict(self):
        # TODO: use unwrap instead?
        out = dict(self.items())
        out['id'] = self.id
        return out

class Annotation(DomainObject):
    type = TextField(default='Annotation')
    annotator_schema_version = TextField(default=u'v1.0')
    uri = TextField()
    account_id = TextField()
    user = DictField()
    text = TextField()
    quote = TextField()
    created = DateTimeField(default=datetime.now)
    ranges = ListField(DictField())
    permissions = DictField(
        Mapping.build(
            read=ListField(TextField()),
            update=ListField(TextField()),
            delete=ListField(TextField()),
            admin=ListField(TextField())
        ))

    def __init__(self, id=None, **values):
        if 'user' in values and isinstance(values['user'], basestring):
            values['user'] = { 'id': values['user'] }
        super(Annotation, self).__init__(id, **values)

    @property
    def userid(self):
        return user['id']

    def update_from_dict(self, dict_):
        if 'id' in dict_:
            del dict_['id']
        if '_id' in dict_:
            del dict_['_id']
        if 'user' in dict_ and isinstance(dict_['user'], basestring):
            dict_['user'] = { 'id': dict_['user'] }

        attrnames = self._fields.keys()
        for k,v in dict_.items():
            if k in attrnames:
                setattr(self, k, v)
            else:
                self[k] = v
        return self

    @classmethod
    def from_dict(cls, dict_):
        if 'id' in dict_:
            ann = Annotation.get(dict_['id'])
        else:
            ann = Annotation()
        ann.update_from_dict(dict_)
        return ann

    @classmethod
    def search(self, **kwargs):
        '''Search by arbitrary attributes.

        WARNING: at the moment use temporary views.
        '''
        non_query_args = ['offset', 'limit', 'all_fields']
        offset = int(kwargs.get('offset', 0))
        limit = int(kwargs.get('limit', -1))
        for k in non_query_args:
            if k in kwargs:
                del kwargs[k]
        terms = kwargs.keys()
        if terms:
            couchkey = '[%s]' % ','.join(['doc.' + x for x in terms])
        else:
            couchkey = 'null'
        map_fun = '''function(doc) {
            if (doc.type == 'Annotation')
                emit(%s, null);
        }''' % couchkey
        wrapper = lambda x: Annotation.wrap(x['doc'])
        ourkwargs = dict(
            map_fun=map_fun,
            offset=offset,
            include_docs=True,
            wrapper=wrapper
            )
        if limit >= 0:
            ourkwargs['limit'] = limit
        q = Metadata.DB.query(**ourkwargs)
        if terms:
            return q[ list(kwargs.values()) ]
        else:
            return q


class Account(DomainObject):
    type = TextField(default='Account')
    username = TextField()
    pwdhash = TextField()
    email = TextField()
    activated = BooleanField(default=True)
    created = DateTimeField(default=datetime.now)
    secret = TextField(default=str(uuid.uuid4()))
    ttl = IntegerField()

    by_email = ViewField('account', '''\
        function(doc) {
            if (doc.type=='Account') {
                emit(doc.email, doc);
            }
       }''')

    @classmethod
    def get_by_email(cls, email):
        out = cls.by_email(Metadata.DB, limit=1)
        return list(out[email])


# Required views
# query by document
# query by user
# query by document and user
# query 
# TODO: general, change from all_fields to include_docs=True ?
# Remove offset ....?
# limit the same
# results format is different: {'total_rows': 3, 'offset':', 'rows': ..
# as opposed to {'total': ,'results': ...}
# could sort this out with a list function ...
def setup_views(db):
    design_doc = 'annotator'
    view = couchdb.design.ViewDefinition(design_doc, 'all', '''
function(doc) {
    emit(doc._id, null);
}
'''
    )
    view.get_doc(db)
    view.sync(db)

    view = couchdb.design.ViewDefinition(design_doc, 'byuri', '''
function(doc) {
    if(doc.uri) {
        emit(doc.uri, null);
    }
}
'''
    )
    view.get_doc(db)
    view.sync(db)

    Account.by_email.get_doc(db)
    Account.by_email.sync(db)


