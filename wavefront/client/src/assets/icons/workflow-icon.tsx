const WorkflowIcon = ({ ...props }: React.SVGProps<SVGSVGElement>) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 16 16" {...props}>
    <path
      stroke="#585858"
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M13.333 9.333a1.333 1.333 0 1 0 0-2.666 1.333 1.333 0 0 0 0 2.666M13.333 4a1.333 1.333 0 1 0 0-2.667 1.333 1.333 0 0 0 0 2.667M13.333 14.667a1.333 1.333 0 1 0 0-2.667 1.333 1.333 0 0 0 0 2.667M2.667 9.333a1.333 1.333 0 1 0 0-2.666 1.333 1.333 0 0 0 0 2.666M4 8h8"
    ></path>
    <path
      stroke="#585858"
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M12 2.667H9.334q-2 0-2 2v6.666q0 2 2 2H12"
    ></path>
  </svg>
);

export default WorkflowIcon;
