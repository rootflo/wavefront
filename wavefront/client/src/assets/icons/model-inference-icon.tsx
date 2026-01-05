const ModelInferenceIcon = ({ ...props }: React.SVGProps<SVGSVGElement>) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 16 16" {...props}>
    <path
      stroke="#585858"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeMiterlimit="10"
      d="M7.333 14.667h3.334C13 14.667 14 13.333 14 11.333V4.667c0-2-1-3.334-3.333-3.334H5.333C3 1.333 2 2.667 2 4.667v4.666"
    ></path>
    <path
      stroke="#585858"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeMiterlimit="10"
      d="M9.667 3v1.333c0 .734.6 1.334 1.333 1.334h1.333M2.667 11.333l-1.333 1.334L2.667 14M4.667 11.333 6 12.667 4.667 14"
    ></path>
  </svg>
);

export default ModelInferenceIcon;
