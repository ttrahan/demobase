# Copyright 2015 Google Inc. All Rights Reserved.

"""A class that creates resource projection specification."""

import copy
import sys


ALIGN_DEFAULT = 'left'
ALIGNMENTS = {'left': lambda s, w: s.ljust(w),
              'center': lambda s, w: s.center(w),
              'right': lambda s, w: s.rjust(w)}


class ProjectionSpec(object):
  """Creates a resource projection specification.

  A resource projection is an expression string that contains a list of resource
  keys with optional attributes. A projector is a method that takes a projection
  specification and a resource object as input and produces a new
  JSON-serializable object containing only the values corresponding to the keys
  in the projection specification.

  Optional projection key attributes may transform the values in the output
  JSON-serializable object. Cloud SDK projection attributes are used for output
  formatting.

  A default or empty projection expression still produces a projector that
  converts a resource to a JSON-serializable object.

  This class is used by the resource projection expression parser to create a
  resource projection specification from a projection expression string.

  Attributes:
    aliases: The short key name alias dictionary.
    _attributes: Projection attributes dict indexed by attribute name.
    _columns: A list of (key,_Attribute) tuples used to project a resource to
      a list of columns.
    _empty: An empty projection _Tree used by Projector().
    _name: The projection name from the expression string.
    _tree: The projection _Tree root, used by
      resource_projector.Evaluate() to efficiently project each resource.
    symbols: Default and caller-defined transform function dict indexed by
      function name.
  """

  DEFAULT = 0  # _Attribute default node flag.
  INNER = 1  # _Attribute inner node flag.
  PROJECT = 2  # _Attribute project node flag.

  class _Column(object):
    """Column key and transform attribute for self._columns.

    Attributes:
      key: The column key.
      attribute: The column key _Attribute.
    """

    def __init__(self, key, attribute):
      self.key = key
      self.attribute = attribute

  def __init__(self, defaults=None, symbols=None):
    """Initializes a projection.

    Args:
      defaults: resource_projection_spec.ProjectionSpec defaults.
      symbols: Transform function symbol table dict indexed by function name.
    """
    self.aliases = {}
    self._attributes = {}
    self._columns = []
    self._empty = None
    self._name = None
    self._snake_headings = {}
    self._snake_re = None
    if defaults:
      self._tree = copy.deepcopy(defaults.GetRoot())
      self.Defaults()
      if defaults.symbols:
        self.symbols = copy.deepcopy(defaults.symbols)
        if symbols:
          self.symbols.update(symbols)
      else:
        self.symbols = symbols if symbols else {}
      self.aliases.update(defaults.aliases)
    else:
      self._tree = None
      self.symbols = symbols

  def _Defaults(self, projection):
    """Defaults() helper -- converts a projection to a default projection.

    Args:
      projection: A node in the original projection _Tree.
    """
    projection.attribute.flag = self.DEFAULT
    projection.attribute.ordinal = None
    for node in projection.tree.values():
      self._Defaults(node)

  def _Print(self, projection, out, level):
    """Print() helper -- prints projection node p and its children.

    Args:
      projection: A _Tree node in the original projection.
      out: The output stream.
      level: The nesting level counting from 1 at the root.
    """
    for key in projection.tree:
      out.write('{indent} {key} : {attribute}\n'.format(
          indent='  ' * level,
          key=key,
          attribute=projection.tree[key].attribute))
      self._Print(projection.tree[key], out, level + 1)

  def _Ordering(self):
    """Collects PROJECT (ordinal, order, attribute) from projection.

    Returns:
      A list of (ordinal, order, attribute) tuples.
    """

    def _DFSOrdering(projection, ordering):
      """Ordering DFS per-node helper.

      Args:
        projection: A _Tree node in the original projection.
        ordering: The list of (ordinal, order, attribute) tuples.
      """
      attribute = projection.attribute
      if attribute.flag == self.PROJECT:
        ordering.append((attribute.ordinal, attribute.order, attribute))
      for p in projection.tree.values():
        _DFSOrdering(p, ordering)

    ordering = []
    _DFSOrdering(self._tree, ordering)
    return ordering

  def AddAttribute(self, name, value):
    """Adds name=value to the attributes.

    Args:
      name: The attribute name.
      value: The attribute value
    """
    self._attributes[name] = value

  def DelAttribute(self, name):
    """Deletes name from the attributes if it is in the attributes.

    Args:
      name: The attribute name.
    """
    if name in self._attributes:
      del self._attributes[name]

  def AddAlias(self, name, key):
    """Adds name as an alias for key to the projection.

    Args:
      name: The short (no dots) alias name for key.
      key: The parsed key to add.
    """
    self.aliases[name] = key

  def AddKey(self, key, attribute):
    """Adds key and attribute to the projection.

    Args:
      key: The parsed key to add.
      attribute: Parsed _Attribute to add.
    """
    self._columns.append(self._Column(key, attribute))

  def SetName(self, name):
    """Sets the projection name.

    The projection name is the rightmost of the names in the expression.

    Args:
      name: The projection name.
    """
    self._name = name

  def GetRoot(self):
    """Returns the projection root node.

    Returns:
      The resource_projector_parser._Tree root node.
    """
    return self._tree

  def SetRoot(self, root):
    """Sets the projection root node.

    Args:
      root: The resource_projector_parser._Tree root node.
    """
    self._tree = root

  def GetEmpty(self):
    """Returns the projector resource_projector_parser._Tree empty node.

    Returns:
      The projector resource_projector_parser._Tree empty node.
    """
    return self._empty

  def SetEmpty(self, node):
    """Sets the projector resource_projector_parser._Tree empty node.

    The empty node is used by to apply [] empty slice projections.

    Args:
      node: The projector resource_projector_parser._Tree empty node.
    """
    self._empty = node

  def Columns(self):
    """Returns the projection columns.

    Returns:
      The columns in the projection, None if the entire resource is projected.
    """
    return self._columns

  def ColumnCount(self):
    """Returns the number of columns in the projection.

    Returns:
      The number of columns in the projection, 0 if the entire resource is
        projected.
    """
    return len(self._columns)

  def Defaults(self):
    """Converts the projection to a default projection.

    A default projection provides defaults for attribute values and function
    symbols. An explicit non-default projection value always overrides the
    corresponding default value.
    """
    if self._tree:
      self._Defaults(self._tree)
    self._columns = []

  def Aliases(self):
    """Returns the short key name alias dictionary.

    This dictionary maps short (no dots) names to parsed keys.

    Returns:
      The short key name alias dictionary.
    """
    return self.aliases

  def Attributes(self):
    """Returns the projection _Attribute dictionary.

    Returns:
      The projection _Attribute dictionary.
    """
    return self._attributes

  def Alignments(self):
    """Returns the projection column justfication list.

    Returns:
      The ordered list of alignment functions, where each function is one of
        ljust [default], center, or rjust.
    """
    return [ALIGNMENTS[attribute.align] for _, _, attribute in
            sorted(self._Ordering())]

  def Labels(self):
    """Returns the ordered list of projection labels.

    Returns:
      The ordered list of projection label strings, None if all labels are
        empty.
    """
    labels = [attribute.label or '' for _, _, attribute in
              sorted(self._Ordering())]
    return labels if any(labels) else None

  def Name(self):
    """Returns the projection name.

    The projection name is the rightmost of the names in the expression.

    Returns:
      The projection name, None if none was specified.
    """
    return self._name

  def Order(self):
    """Returns the projection sort key order suitable for use by sorted().

    Example:
      projection = resource_projector.Compile('...')
      order = projection.Order()
      if order:
        rows = sorted(rows, key=itemgetter(*order))

    Returns:
      The list of sort key indices, None if projection is None or if all sort
        order indices in the projection are None (unordered).
    """
    return [column - 1 for column, order, _ in
            sorted(self._Ordering(), key=lambda x: x[1])
            if order is not None] or None

  def Print(self, out=sys.stdout):
    """Prints the projection with indented nesting.

    Args:
      out: The output stream, sys.stdout if None.
    """
    if self._tree:
      self._Print(self._tree, out, 1)

  def Tree(self):
    """Returns the projection tree root.

    Returns:
      The projection tree root.
    """
    return self._tree
