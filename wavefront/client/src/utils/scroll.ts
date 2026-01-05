export const scrollToBottom = (id: string, behavior: ScrollBehavior = 'smooth') => {
  setTimeout(() => {
    const element = document.getElementById(id);
    element?.scrollTo({
      left: 0,
      top: element?.scrollHeight,
      behavior: behavior,
    });
  }, 0);
};
