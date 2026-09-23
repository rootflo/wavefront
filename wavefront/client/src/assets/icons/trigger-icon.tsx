const TriggerIcon = ({ ...props }: React.SVGProps<SVGSVGElement>) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 16 16" {...props}>
    <path
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M8.667 1.333 3.333 9.333h4l-.667 5.334 5.334-8H8l.667-5.334Z"
    />
  </svg>
);

export default TriggerIcon;
