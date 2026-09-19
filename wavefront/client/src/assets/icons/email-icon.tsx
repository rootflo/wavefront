const EmailIcon = ({ ...props }: React.SVGProps<SVGSVGElement>) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 16 16" {...props}>
    <rect
      x="1.333"
      y="3.333"
      width="13.333"
      height="9.333"
      rx="1.333"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      d="m1.833 4.167 5.36 4.02a1.333 1.333 0 0 0 1.6 0l5.36-4.02"
    />
  </svg>
);

export default EmailIcon;
