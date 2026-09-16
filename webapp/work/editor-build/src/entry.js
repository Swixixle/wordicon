// The editor bundle's entry: everything the structured editor adapter needs
// from ProseMirror, re-exported once. Built by build.mjs into
// webapp/work/vendor/prosemirror.js (ESM, no CDN, loaded locally).
export { Schema, Node, Fragment, Slice, DOMParser, DOMSerializer } from 'prosemirror-model';
export { EditorState, TextSelection, Selection, Plugin, PluginKey, NodeSelection, AllSelection } from 'prosemirror-state';
export { EditorView, Decoration, DecorationSet } from 'prosemirror-view';
export { Transform, ReplaceStep, Mapping } from 'prosemirror-transform';
export { history, undo, redo, closeHistory, undoDepth, redoDepth } from 'prosemirror-history';
export { keymap } from 'prosemirror-keymap';
export { baseKeymap, toggleMark, setBlockType, wrapIn, lift, chainCommands, exitCode, joinUp, joinDown, selectParentNode, splitBlock, newlineInCode, createParagraphNear, liftEmptyBlock, deleteSelection, joinBackward, joinForward, selectNodeBackward, selectNodeForward } from 'prosemirror-commands';
export { wrapInList, splitListItem, liftListItem, sinkListItem } from 'prosemirror-schema-list';
