import { EditorView } from '@uiw/react-codemirror';

export const popupCodeMirrorExtensions = [
  EditorView.lineWrapping,
  EditorView.theme({
    '&': {
      width: '100%',
      maxWidth: '100%',
    },
    '.cm-scroller': {
      overflowX: 'hidden',
      overflowY: 'auto',
    },
    '.cm-content': {
      minWidth: '0 !important',
    },
  }),
];
