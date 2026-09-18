const ChatIcon = ({ ...props }: React.SVGProps<SVGSVGElement>) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="none" viewBox="0 0 14 14" {...props}>
    <path
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeMiterlimit="10"
      d="M4.667 12.25H4.2c-1.867 0-2.8-.933-2.8-2.8V4.55c0-1.867.933-2.8 2.8-2.8h5.6c1.867 0 2.8.933 2.8 2.8v4.9c0 1.867-.933 2.8-2.8 2.8H9.1L7 13.883a.44.44 0 0 1-.7 0z"
    ></path>
    <path
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M4.433 6.417h5.134M4.433 8.75h3.267"
    ></path>
  </svg>
);

export default ChatIcon;
