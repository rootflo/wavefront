import { useThemeStore } from '@app/store/theme-store';
import CodeMirror, { ReactCodeMirrorProps } from '@uiw/react-codemirror';

/** CodeMirror that follows the app's light/dark theme unless a theme is passed explicitly. */
const CodeEditor = (props: ReactCodeMirrorProps) => {
  const theme = useThemeStore((state) => state.theme);
  return <CodeMirror theme={theme} {...props} />;
};

export default CodeEditor;
