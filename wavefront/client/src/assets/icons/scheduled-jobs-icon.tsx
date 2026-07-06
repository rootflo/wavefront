const ScheduledJobsIcon = ({ ...props }: React.SVGProps<SVGSVGElement>) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 16 16" {...props}>
    <path
      stroke="#585858"
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M8 2.667v2.666M8 10.667v2.666M4 8H2.667M13.333 8H12M4.343 4.343l1.886 1.886M9.771 9.771l1.886 1.886M4.343 11.657l1.886-1.886M9.771 6.229l1.886-1.886"
    />
    <circle cx="8" cy="8" r="2.667" stroke="#585858" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export default ScheduledJobsIcon;
