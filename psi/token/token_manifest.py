from atom.api import Unicode, Typed
from enaml.core.api import d_
from enaml.workbench.api import PluginManifest, Extension, Plugin


class TokenManifest(PluginManifest):
    '''
    Defines a manifest that will be generated on the fly
    '''
    base = d_(Unicode())
    compact_base = d_(Unicode())
    label_base = d_(Unicode())
    scope = d_(Unicode())

    def __init__(self, base, scope, label_base=None, compact_base=None):
        if label_base is None:
            label_base = base.capitalize()
        if compact_base is None:
            compact_base = label_base[:3] + '.'
        super(TokenManifest, self).__init__(base=base,
                                            scope=scope,
                                            label_base=label_base,
                                            compact_base=compact_base)